"""ROAM bridge -- hub events out to the phone, until the Channels app exists.

The hub holds everything and pushes it over a WebSocket, but nothing was
listening, so from across the room the whole thing was a database. This service
subscribes to the hub like any other client and forwards the events worth
interrupting someone for to ROAM Touch via `tools/roam-push`.

Two rules it exists to honour:

* **The channel label leads the message.** "✳ Augment things: build finished"
  tells you which session is talking without unlocking anything. A notification
  that does not say who is speaking is noise.
* **Reply where the last message came from.** He typed the prompt in tmux, so
  the answer stays in tmux; he sent it from ROAM, so the answer buzzes on ROAM.
  The hub stamps that onto every event as `coverage`; the bridge just reads it.

⚠️ It shells out to `roam-push`, **never to `roam-msg`**. They used to be the
same program, which was the whole architectural bug: `roam-msg` is what agents
call, and it now posts a `notice` to the hub -- so a bridge that delivered
through it would turn every notification into a new notice and feed itself
forever. `roam-push` is the device transport and nothing else; this is the only
thing that runs it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable

from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger("roam.bridge")

HUB_DIR = Path(__file__).resolve().parent
BRIDGE_VERSION = "1.0.0"

#: Which event kinds are worth a buzz on someone's arm.
#:
#: `outcome` is the answer he walked away to wait for, `error` is a send that
#: never reached the pane, and `notice` is a tool telling him something
#: directly (`roam-msg "build finished"`) -- all three are news. `receipt` is
#: deliberately absent: he typed that himself seconds ago, and echoing it back
#: to his wrist is exactly the noise that makes people take a device off.
#: `sent`, `opened` and `closed` are bookkeeping the panel can show when he
#: looks.
#:
#: This will get tuned -- change the tuple, not a condition buried in a branch.
PUSH_KINDS: tuple[str, ...] = ("outcome", "error", "notice")

#: Prefixes by kind. An error must not read like an answer.
KIND_PREFIX: dict[str, str] = {"error": "⚠️ "}

#: ⚠️ A circuit breaker, **not the rule**.
#:
#: The rule is per-event coverage: an event that landed while he was covered is
#: never pushed, and an event that landed while he was absent always is --
#: whether that is one event or thirty. Owner, 2026-08-11: *"15 was just an
#: example… we need a source to verify if I genuinely missed 3 messages or I
#: just responded on my laptop and don't need notified."* Backlog size was his
#: proxy for that question; `coverage` on each event answers it directly, so
#: size no longer decides anything.
#:
#: This remains only to stop a pathological flood -- a hub outage replaying
#: hundreds of genuinely-uncovered events -- from machine-gunning the phone.
#: Reaching it means something is wrong, so it logs a warning, and the events
#: are still in the hub and the channel history.
BACKLOG_FLOOD_LIMIT = 50


class Settings(BaseSettings):
    """Every field is settable as `ROAM_BRIDGE_<FIELD>`."""

    model_config = SettingsConfigDict(env_prefix="ROAM_BRIDGE_", extra="ignore")

    hub_url: str = "http://100.67.237.109:8787"
    token_file: Path = HUB_DIR / "hub-token.txt"
    token: str | None = None
    state_file: Path = HUB_DIR / "bridge-state.json"
    #: The device transport. ⚠️ Never point this at `roam-msg` -- see the
    #: module docstring; that is a feedback loop, not a configuration choice.
    roam_push: Path = Path.home() / "Projects/roam/tools/roam-push"

    #: Honour the hub's coverage stamp: don't push into a conversation that is
    #: already happening somewhere he can see. False pushes everything.
    suppress_when_covered: bool = True
    #: Circuit breaker only -- see BACKLOG_FLOOD_LIMIT.
    backlog_flood_limit: int = BACKLOG_FLOOD_LIMIT

    #: Rate limit: at most one notification per this many seconds. Events that
    #: arrive inside the window are coalesced per channel, newest wins.
    min_interval_s: float = 5.0
    #: Hard ceiling on how many channels can be queued; the oldest is dropped
    #: (its newer sibling is already in the queue) rather than growing forever.
    max_queued_channels: int = 20

    label_chars: int = 32
    summary_chars: int = 120

    #: `roam-push` blocks for ~75 s when the phone is off the tailnet (adb
    #: connect, measured 2026-08-11), so it must always be bounded and the
    #: child killed -- otherwise one sleeping phone stalls every notification
    #: and leaves orphan adb processes behind.
    roam_push_timeout_s: float = 20.0
    #: After a failed push, stop trying for this long. A phone that is asleep
    #: stays asleep; burning 20 s per queued event achieves nothing.
    offline_backoff_s: float = 60.0
    #: How many times one notification may be attempted before it is dropped.
    #: The hub still holds it -- the panel shows it when he looks.
    max_attempts: int = 2

    reconnect_max_s: float = 30.0
    log_level: str = "info"


def load_token(settings: Settings) -> str:
    if settings.token:
        return settings.token
    return Path(settings.token_file).read_text(encoding="utf-8").strip()


def trim(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def compose(
    label: str,
    summary: str,
    kind: str,
    extra: int = 0,
    label_chars: int = 32,
    summary_chars: int = 120,
) -> str:
    """`✳ Augment things: the suite is green — 122 tests. (+2 more)`"""
    head = trim(label, label_chars) or "channel"
    body = trim(summary, summary_chars)
    text = f"{KIND_PREFIX.get(kind, '')}{head}: {body}".strip()
    if extra > 0:
        text += f" (+{extra} more)"
    return text


class State:
    """The cursor, on disk, so a restart neither replays nor skips."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.last_event_id: int | None = None
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        value = data.get("last_event_id")
        if isinstance(value, int) and value >= 0:
            self.last_event_id = value

    def remember(self, event_id: int) -> None:
        if self.last_event_id is not None and event_id <= self.last_event_id:
            return
        self.last_event_id = event_id
        tmp = self.path.with_suffix(".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(
                json.dumps({"last_event_id": event_id}), encoding="utf-8"
            )
            tmp.replace(self.path)  # atomic: a torn state file loses events
        except OSError as exc:
            log.warning("cannot persist bridge state: %s", exc)


async def push_via_roam_push(
    settings: Settings, text: str, pane_id: str
) -> bool:
    """Run `roam-push`, the device transport. Never raises; the bridge
    outlives a failed push.

    `--tag` groups the notification per channel so two sessions do not
    overwrite each other on the phone.
    """
    tag = pane_id.lstrip("%@") or "0"
    try:
        proc = await asyncio.create_subprocess_exec(
            str(settings.roam_push),
            "--tag",
            tag,
            text,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=settings.roam_push_timeout_s
            )
        except asyncio.TimeoutError:
            # wait_for cancels the await, not the process. Kill it, or every
            # unreachable phone leaves an adb connect running for 75 s.
            proc.kill()
            await proc.wait()
            log.warning("roam-push timed out after %.0fs", settings.roam_push_timeout_s)
            return False
    except (OSError, ValueError) as exc:
        log.warning("roam-push failed to start: %s", exc)
        return False
    if proc.returncode != 0:
        log.warning("roam-push exited %s: %s", proc.returncode, stderr.decode().strip())
        return False
    return True


class Bridge:
    """Hub WebSocket in, `roam-push` out.

    `pusher` and `watched_panes` are injected so the network and tmux
    boundaries can be faked; everything above them is the real policy.
    """

    def __init__(
        self,
        settings: Settings,
        pusher: Callable[[str, str], Awaitable[bool]] | None = None,
        state: State | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.settings = settings
        self.state = state or State(settings.state_file)
        self.clock = clock or time.monotonic
        self._pusher = pusher or (
            lambda text, pane: push_via_roam_push(settings, text, pane)
        )
        self.labels: dict[str, str] = {}
        #: pane_id -> (summary, kind, coalesced_count)
        self._queue: dict[str, tuple[str, str, int, int]] = {}
        self._last_push_at = float("-inf")  # the first event is never delayed
        self._offline_until = float("-inf")
        self.dropped = 0
        self.pushed: list[tuple[str, str]] = []  # (pane_id, text), for tests
        self.suppressed = 0
        self.skipped_backlogs = 0

    # ------------------------------------------------------------- policy

    def learn_channels(self, payload: Iterable[dict[str, Any]]) -> None:
        for channel in payload or []:
            pane_id = channel.get("pane_id")
            if pane_id:
                self.labels[pane_id] = channel.get("label") or pane_id

    def label_for(self, pane_id: str) -> str:
        return self.labels.get(pane_id, pane_id)

    def wants(self, event: dict[str, Any]) -> bool:
        return event.get("kind") in PUSH_KINDS

    def was_covered(self, event: dict[str, Any]) -> bool:
        """Was the conversation already where this event landed?

        The hub stamps the answer onto the event when it happens, from one
        rule -- **reply where the last message came from**. He typed the prompt
        in tmux, so he is reading the answer there; he sent it from ROAM, so
        that is where it goes.

        The bridge therefore holds no opinion and asks nothing: a live push and
        a replayed one read the same stamp, so nothing is judged twice, and a
        backlog is answerable however old it is.

        ⚠️ Unknown means **not covered** -- push. A hub too old to stamp, a
        failed lookup, a fresh pane: none of them may become silence.
        """
        if not self.settings.suppress_when_covered:
            return False
        coverage = event.get("coverage")
        if isinstance(coverage, dict) and coverage.get("known"):
            return bool(coverage.get("covered"))
        return False

    def enqueue(self, event: dict[str, Any]) -> None:
        pane_id = event.get("pane_id") or ""
        summary = event.get("summary") or event.get("body") or ""
        kind = event.get("kind") or ""
        previous = self._queue.get(pane_id)
        extra = previous[2] + 1 if previous else 0
        self._queue[pane_id] = (summary, kind, extra, 0)
        while len(self._queue) > self.settings.max_queued_channels:
            self._queue.pop(next(iter(self._queue)))

    # -------------------------------------------------------------- frames

    async def handle_frame(self, frame: dict[str, Any]) -> None:
        kind = frame.get("type")
        if kind == "hello":
            self.learn_channels(frame.get("channels"))
            if self.state.last_event_id is None:
                # First ever run: start from now. Replaying a week of outcomes
                # onto someone's arm is not a welcome.
                self.state.remember(int(frame.get("latest_event_id") or 0))
        elif kind in ("channels",):
            self.learn_channels(frame.get("channels"))
        elif kind == "channel":
            self.learn_channels([frame.get("channel") or {}])
        elif kind == "backlog":
            await self.handle_backlog(frame.get("events") or [])
        elif kind == "event":
            await self.handle_event(frame.get("event") or {})

    async def handle_backlog(self, events: list[dict[str, Any]]) -> None:
        """Catch up on what happened while we were away.

        Each event decides for itself, from the coverage stamped on it when it
        happened: the ones he was present for pass silently, the ones he
        genuinely missed are pushed. Size is not the arbiter -- three missed
        outcomes are worth telling him about, and thirty answered from the
        laptop are not.

        `BACKLOG_FLOOD_LIMIT` is the only size check left, and it is a circuit
        breaker: see its comment.
        """
        fresh = [
            e
            for e in events
            if isinstance(e.get("id"), int)
            and (self.state.last_event_id is None or e["id"] > self.state.last_event_id)
        ]
        missed = sum(1 for e in fresh if self.wants(e) and not self.was_covered(e))
        if missed > self.settings.backlog_flood_limit:
            log.warning(
                "%d genuinely missed notifications (>%d) -- flood valve tripped, "
                "staying quiet; they are all in the channels",
                missed,
                self.settings.backlog_flood_limit,
            )
            for event in fresh:
                if isinstance(event.get("id"), int):
                    self.state.remember(event["id"])
            self.skipped_backlogs += 1
            return
        for event in events:
            await self.handle_event(event)

    async def handle_event(self, event: dict[str, Any]) -> None:
        event_id = event.get("id")
        if not isinstance(event_id, int):
            return
        if self.state.last_event_id is not None and event_id <= self.state.last_event_id:
            return  # already seen; a reconnect replayed it
        self.state.remember(event_id)
        if not self.wants(event):
            return
        pane_id = event.get("pane_id") or ""
        if self.was_covered(event):
            # He was looking at this channel when it landed. It was never a
            # missed message -- it stays in the thread, it just never buzzes.
            self.suppressed += 1
            by = ",".join((event.get("coverage") or {}).get("by") or []) or "presence"
            log.info(
                "not a missed message: %s on %s was covered by %s",
                event.get("kind"),
                pane_id,
                by,
            )
            return
        self.enqueue(event)
        await self.drain()

    # -------------------------------------------------------------- output

    async def drain(self) -> None:
        """Send at most one notification per `min_interval_s`."""
        now = self.clock()
        if not self._queue:
            return
        if now - self._last_push_at < self.settings.min_interval_s:
            return
        if now < self._offline_until:
            return  # the phone was unreachable a moment ago; let it be
        pane_id, (summary, kind, extra, attempts) = next(iter(self._queue.items()))
        del self._queue[pane_id]
        text = compose(
            self.label_for(pane_id),
            summary,
            kind,
            extra,
            self.settings.label_chars,
            self.settings.summary_chars,
        )
        self._last_push_at = now
        ok = await self._pusher(text, pane_id)
        self.pushed.append((pane_id, text))
        if ok:
            log.info("pushed %s: %s", pane_id, text)
            return
        # Failed: almost always a phone that is asleep or off the tailnet.
        self._offline_until = now + self.settings.offline_backoff_s
        attempts += 1
        if attempts >= self.settings.max_attempts:
            self.dropped += 1
            log.warning(
                "dropping after %d attempts (phone unreachable?): %s", attempts, text
            )
            return
        log.warning("push failed, will retry once: %s", text)
        # Re-inserted at the back: everything else queued gets a turn first.
        self._queue[pane_id] = (summary, kind, extra, attempts)

    async def flush_loop(self, stop: asyncio.Event) -> None:
        """Drain the coalescing queue on a timer, not only on arrival."""
        while not stop.is_set():
            await asyncio.sleep(max(0.05, self.settings.min_interval_s / 2))
            await self.drain()

    # ----------------------------------------------------------- the socket

    def ws_url(self) -> str:
        base = self.settings.hub_url.rstrip("/")
        base = base.replace("https://", "wss://").replace("http://", "ws://")
        url = f"{base}/ws"
        if self.state.last_event_id is not None:
            url += f"?since={self.state.last_event_id}"
        return url

    async def run(self, stop: asyncio.Event | None = None) -> None:
        import websockets

        stop = stop or asyncio.Event()
        token = load_token(self.settings)
        backoff = 1.0
        flusher = asyncio.create_task(self.flush_loop(stop))
        try:
            while not stop.is_set():
                try:
                    async with websockets.connect(
                        self.ws_url(),
                        additional_headers={"Authorization": f"Bearer {token}"},
                        ping_interval=20,
                        ping_timeout=60,
                    ) as socket:
                        log.info("connected to %s", self.ws_url())
                        backoff = 1.0
                        async for raw in socket:
                            try:
                                frame = json.loads(raw)
                            except json.JSONDecodeError:
                                continue
                            if isinstance(frame, dict):
                                await self.handle_frame(frame)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    log.warning("hub connection lost (%s); retrying in %.0fs", exc, backoff)
                    await asyncio.sleep(backoff)
                    backoff = min(self.settings.reconnect_max_s, backoff * 2)
        finally:
            flusher.cancel()
            try:
                await flusher
            except (asyncio.CancelledError, Exception):
                pass


def main() -> None:
    settings = Settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    log.info(
        "roam-bridge %s -> %s (push %s; coverage suppression %s; flood valve %d)",
        BRIDGE_VERSION,
        settings.hub_url,
        "/".join(PUSH_KINDS),
        "on" if settings.suppress_when_covered else "off",
        settings.backlog_flood_limit,
    )
    asyncio.run(Bridge(settings).run())


if __name__ == "__main__":
    main()
