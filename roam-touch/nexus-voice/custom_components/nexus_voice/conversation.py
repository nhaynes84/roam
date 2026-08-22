"""The conversation agent: spoken words in, a channel decision out.

Everything this file knows about is Home Assistant objects. The decisions live
in `matcher.py` (which channel) and `runtime.py` (what is cached, who is owed
an answer), both of which are unit-tested without HA.

## Why nothing here waits for Claude

Assist is a synchronous pipeline: it wants a response in about a second so the
satellite can speak it. A Claude turn takes thirty seconds to several minutes.
So this **never returns the answer**. It acknowledges, hands the prompt to the
hub, and the answer arrives later as a spoken announcement via `runtime`.

That is not a workaround -- it is the shape the hub already has. A receipt now,
an outcome later. Trying to block here would time out the pipeline and leave
the wearer with silence and no idea whether he was heard.
"""

from __future__ import annotations

import asyncio
import logging

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.intent import IntentResponse

from .const import CONF_DEFAULT_SPEAKER, DOMAIN, TRIGGER_WORD
from .hub import HubError
from .matcher import match
from .phrasing import label_for, strip_trigger

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([NexusConversationEntity(entry, hass.data[DOMAIN][entry.entry_id])])


class NexusConversationEntity(conversation.ConversationEntity):
    _attr_has_entity_name = True
    _attr_name = "Nexus"

    def __init__(self, entry: ConfigEntry, runtime) -> None:
        self._entry = entry
        self._runtime = runtime
        self._attr_unique_id = f"{entry.entry_id}-conversation"
        #: conversation_id -> the labels we asked him to choose between.
        self._awaiting: dict[str, list[str]] = {}

    @property
    def supported_languages(self) -> list[str]:
        return ["en"]

    # -- the one entry point ----------------------------------------------

    async def async_process(
        self, user_input: conversation.ConversationInput
    ) -> conversation.ConversationResult:
        text = strip_trigger(user_input.text)
        speaker = self._resolve_speaker(user_input)

        if not text:
            return self._reply(user_input, "Nexus is listening.", continue_conversation=True)

        # A clarification he is answering ("Gaggia Build") narrows the field to
        # what we offered, so a one-word reply routes cleanly.
        pending = self._awaiting.pop(user_input.conversation_id or "", None)

        try:
            candidates = await self._runtime.candidates()
        except Exception as exc:  # noqa: BLE001 -- never fail an utterance
            _LOGGER.exception("channel index unavailable")
            return self._reply(user_input, f"I couldn't reach the hub: {exc}")

        if pending:
            candidates = [c for c in candidates if c.label in pending] or candidates

        vector = await self._runtime.embedder.embed(text)
        decision = match(text, candidates, target_vector=vector)

        if decision.kind == "ambiguous":
            self._awaiting[user_input.conversation_id or ""] = list(decision.alternatives)
            options = " or ".join(decision.alternatives)
            return self._reply(
                user_input, f"Which one -- {options}?", continue_conversation=True
            )

        if decision.routed:
            return await self._deliver(user_input, text, decision.pane_id, decision.label, speaker)

        return await self._spawn(user_input, text, speaker)

    # -- the two outcomes --------------------------------------------------

    async def _deliver(self, user_input, text, pane_id, label, speaker):
        try:
            await self._runtime.hub.send(pane_id, text)
        except HubError as exc:
            _LOGGER.error("send to %s failed: %s", pane_id, exc)
            return self._reply(user_input, f"I couldn't send that to {label}.")
        self._runtime.expect_answer(pane_id, speaker, label)
        return self._reply(user_input, f"Sent to {label}.")

    async def _spawn(self, user_input, text, speaker):
        """Start a channel for something that has none.

        ⚠️ Spawning is tmux plus an agent boot -- seconds, not milliseconds.
        Doing it inline would blow the pipeline's timeout, so it acknowledges
        first and the work happens in the background. If the spawn fails he
        hears nothing more, which is why the failure is logged loudly.
        """
        label = label_for(text)

        async def run() -> None:
            try:
                channel = await self._runtime.hub.spawn(label=label)
                pane_id = channel["pane_id"]
                await self._runtime.hub.send(pane_id, text)
                self._runtime.expect_answer(pane_id, speaker, label)
                await self._runtime.refresh()
            except (HubError, KeyError) as exc:
                _LOGGER.error("spawn for %r failed: %s", label, exc)
                if speaker:
                    await self._runtime._speak(speaker, f"I couldn't start a channel for {label}.")

        asyncio.create_task(run())
        return self._reply(user_input, f"Starting a channel for {label}.")

    # -- helpers -----------------------------------------------------------

    def _resolve_speaker(self, user_input: conversation.ConversationInput) -> str:
        """Which media player should say the answer.

        Prefers a media_player on the same device as the satellite that heard
        him -- HA hands us `satellite_id`, so this needs no identity scheme of
        our own. Falls back to the configured default, which is what makes the
        whole loop testable on a Sonos before any satellite exists.
        """
        default = self._entry.options.get(
            CONF_DEFAULT_SPEAKER, self._entry.data.get(CONF_DEFAULT_SPEAKER, "")
        )
        satellite = getattr(user_input, "satellite_id", None)
        if not satellite:
            return default
        registry = er.async_get(self.hass)
        entry = registry.async_get(satellite)
        if not entry or not entry.device_id:
            return default
        devices = dr.async_get(self.hass)
        if not devices.async_get(entry.device_id):
            return default
        for candidate in er.async_entries_for_device(registry, entry.device_id):
            if candidate.domain == "media_player":
                return candidate.entity_id
        return default

    def _reply(self, user_input, speech: str, continue_conversation: bool = False):
        response = IntentResponse(language=user_input.language)
        response.async_set_speech(speech)
        return conversation.ConversationResult(
            response=response,
            conversation_id=user_input.conversation_id,
            continue_conversation=continue_conversation,
        )
