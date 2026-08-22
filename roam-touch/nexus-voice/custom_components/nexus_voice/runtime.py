"""The moving parts behind the conversation agent.

Owns the channel index, the embedding cache, the hub WebSocket, and the map of
"which speaker is waiting for an answer from which pane". The conversation
entity is deliberately thin glue on top of this -- it translates HA objects in
and out and decides nothing.

## Why there is no memcached here

The hub's WebSocket is already a change feed: `ws?since=<id>` replays anything
missed and pushes everything after, so a subscriber never polls and never has
a staleness window. An in-process dict fed by that stream is strictly better
than an external cache -- fewer daemons, no TTL to tune, no chance of serving
a channel that closed a minute ago.

The expensive thing worth caching is not the channel list, which is small and
free. It is the **per-channel embedding**, which costs a round trip. Those are
keyed by document text, so a drifting label invalidates itself.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass

import aiohttp

from .const import DELIVERY_TTL_S
from .embeddings import Embedder
from .hub import HubClient, HubError
from .matcher import Candidate

_LOGGER = logging.getLogger(__name__)

#: How many recent events form a channel's "what is this about" document.
#: Enough to carry vocabulary the label does not (the espresso pane's history
#: is full of OPV, gaskets and portafilters while its label just says "Gaggia
#: Build"), few enough to re-embed cheaply when it moves on.
HISTORY_DEPTH = 12


@dataclass
class Delivery:
    """A spoken answer that is owed to a speaker."""

    pane_id: str
    speaker: str          # media_player entity id
    label: str
    created: float

    @property
    def expired(self) -> bool:
        return time.time() - self.created > DELIVERY_TTL_S


class NexusRuntime:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        hub: HubClient,
        embedder: Embedder,
        speak,
    ):
        self._session = session
        self.hub = hub
        self.embedder = embedder
        #: async callable (speaker_entity_id, text) -> None. Injected so this
        #: module never imports Home Assistant and stays unit-testable.
        self._speak = speak
        self._channels: dict[str, dict] = {}
        self._docs: dict[str, str] = {}
        self._pending: dict[str, Delivery] = {}
        self._ws_task: asyncio.Task | None = None
        self._stale: set[str] = set()

    # -- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        await self.refresh()
        self._ws_task = asyncio.create_task(self._watch())

    async def stop(self) -> None:
        if self._ws_task:
            self._ws_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ws_task
            self._ws_task = None

    # -- channel index -----------------------------------------------------

    async def refresh(self) -> None:
        try:
            channels = await self.hub.channels()
        except HubError as exc:
            _LOGGER.warning("channel refresh failed: %s", exc)
            return
        self._channels = {c["pane_id"]: c for c in channels}
        self._stale.update(self._channels)

    async def candidates(self) -> list[Candidate]:
        """Live channels with embeddings, refreshing any stale documents."""
        out: list[Candidate] = []
        for pane_id, ch in self._channels.items():
            if not ch.get("live", True):
                continue
            doc = await self._document(pane_id, ch)
            vector = await self.embedder.embed(doc, cache=True) if doc else None
            out.append(
                Candidate(
                    pane_id=pane_id,
                    label=ch.get("label") or pane_id,
                    cwd=ch.get("cwd", ""),
                    live=True,
                    status=ch.get("status", "idle"),
                    vector=vector,
                )
            )
        self.embedder.forget(set(self._docs.values()))
        return out

    async def _document(self, pane_id: str, channel: dict) -> str:
        """Label plus recent history -- the text a channel is matched on.

        ★ Measured: embedding the LABEL ALONE does not work. "the espresso
        notes" scored 0.365 against "Gaggia Build" while an unrelated "jeep
        brake booster" scored 0.504 against the same channel. Short proper
        nouns carry almost no signal in nomic-embed-text. Adding the recent
        history is what separates them.
        """
        if pane_id not in self._stale and pane_id in self._docs:
            return self._docs[pane_id]
        label = channel.get("label") or ""
        parts, seen = [label], set()
        try:
            for event in await self.hub.history(pane_id, HISTORY_DEPTH):
                text = (event.get("summary") or event.get("body") or "")[:400]
                if text and text not in seen:
                    seen.add(text)
                    parts.append(text)
        except HubError as exc:
            _LOGGER.debug("history for %s unavailable: %s", pane_id, exc)
        self._docs[pane_id] = "\n".join(parts)
        self._stale.discard(pane_id)
        return self._docs[pane_id]

    # -- delivery ----------------------------------------------------------

    def expect_answer(self, pane_id: str, speaker: str, label: str) -> None:
        """Remember that `speaker` asked `pane_id` something.

        ★ This is the hub's own coverage rule -- *reply where the last message
        came from* -- with one new place in it. He spoke to the kitchen, so the
        kitchen answers.
        """
        if speaker:
            self._pending[pane_id] = Delivery(pane_id, speaker, label, time.time())

    def _take_delivery(self, pane_id: str) -> Delivery | None:
        delivery = self._pending.pop(pane_id, None)
        if delivery and delivery.expired:
            _LOGGER.debug("delivery for %s expired unspoken", pane_id)
            return None
        return delivery

    # -- the hub's event stream -------------------------------------------

    async def _watch(self) -> None:
        """Follow the hub and speak outcomes that a satellite is waiting for.

        ⚠️ Reconnects forever with a backoff. The hub is a launchd job on a
        box that gets rebooted; a WS that dies quietly and never returns would
        present as "voice stopped answering" with nothing in any log.
        """
        backoff = 1
        while True:
            try:
                async with self._session.ws_connect(self.hub.ws_url, heartbeat=30) as ws:
                    _LOGGER.info("nexus_voice: hub stream connected")
                    backoff = 1
                    async for msg in ws:
                        if msg.type is aiohttp.WSMsgType.TEXT:
                            await self._on_frame(msg.json())
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 -- must never exit the loop
                _LOGGER.warning("hub stream dropped (%s); retrying in %ss", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

    async def _on_frame(self, frame: dict) -> None:
        kind = frame.get("type") or frame.get("kind")
        if kind == "channels":
            channels = frame.get("channels", [])
            self._channels = {c["pane_id"]: c for c in channels}
            return

        event = frame.get("event") or (frame if "kind" in frame else None)
        if not isinstance(event, dict):
            return
        pane_id = event.get("pane_id")
        if pane_id:
            # Any new traffic means this channel is about something slightly
            # different than it was; its document needs re-embedding.
            self._stale.add(pane_id)
        if event.get("kind") not in ("outcome", "error"):
            return

        delivery = self._take_delivery(pane_id) if pane_id else None
        if not delivery:
            return
        # ★ Speak the SUMMARY, never the body. It is capped at 280 chars with
        # markdown and code stripped -- built for exactly this. It also happens
        # to be the only length that works on a satellite with no acoustic echo
        # cancellation, which cannot hear you interrupt it.
        text = event.get("summary") or event.get("body") or ""
        if text:
            await self._speak(delivery.speaker, text)
