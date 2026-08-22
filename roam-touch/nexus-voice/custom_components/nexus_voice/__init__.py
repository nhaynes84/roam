"""Nexus Voice -- speak to the ROAM Touch channels through Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_HUB_TOKEN,
    CONF_HUB_URL,
    CONF_OLLAMA_URL,
    DEFAULT_OLLAMA_URL,
    DOMAIN,
)
from .embeddings import Embedder
from .hub import HubClient, HubError
from .runtime import NexusRuntime

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.CONVERSATION]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    hub = HubClient(session, entry.data[CONF_HUB_URL], entry.data[CONF_HUB_TOKEN])

    try:
        health = await hub.health()
        _LOGGER.info("nexus_voice: hub %s build %s", health.get("version"),
                     health.get("build", {}).get("commit"))
    except HubError as exc:
        # Raising ConfigEntryNotReady would be the textbook move, but the hub
        # is a launchd job that comes back on its own and the runtime already
        # reconnects forever. Failing setup would need a manual reload later.
        _LOGGER.warning("nexus_voice: hub unreachable at startup (%s); will retry", exc)

    async def speak(speaker: str, text: str) -> None:
        """Say something on a media player.

        ⚠️ This is the ONLY audio this integration ever produces, and it only
        ever fires for an answer he asked for by voice on that device. It must
        never widen into announcing arbitrary channel traffic: auto-speak was
        built into the Channels app once and killed within the hour --
        "I don't want it non stop blabbering at me."
        """
        if not speaker:
            _LOGGER.debug("no speaker for reply: %s", text[:60])
            return
        try:
            await hass.services.async_call(
                "tts",
                "speak",
                {"entity_id": "tts.piper", "media_player_entity_id": speaker, "message": text},
                blocking=False,
            )
        except Exception:  # noqa: BLE001 -- a failed announcement must not kill the stream
            _LOGGER.exception("failed to speak on %s", speaker)

    embedder = Embedder(session, entry.data.get(CONF_OLLAMA_URL, DEFAULT_OLLAMA_URL))
    runtime = NexusRuntime(session, hub, embedder, speak)
    await runtime.start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        runtime = hass.data[DOMAIN].pop(entry.entry_id, None)
        if runtime:
            await runtime.stop()
    return unloaded
