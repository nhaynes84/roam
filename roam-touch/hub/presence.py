"""Reported presence -- "I am looking at the panel right now".

Almost all of what this module used to do is gone, and deliberately. The rule
that decides whether a notification reaches the arm is now **reply where the
last message came from** (`store.set_channel_input`, `hub._coverage_for`): if he
typed the prompt in tmux, the answer stays in tmux; if he sent it from ROAM, the
answer goes to ROAM. Exactly like any messaging app.

The tmux-client observation this module used to do -- watching `client_activity`,
mapping ttys to logins via `who` -- was only ever a proxy for that question, and
is deleted. So is `HIDIdleTime`, tested and rejected because it read 13.2 hours
idle while he was actively typing over SSH.

What survives is the one signal the last-input rule cannot express: **the app
saying it is foregrounded.** He can be looking at the panel without having sent
anything, and buzzing about the screen already in his hand is noise. It can only
ever *add* suppression on top of the last-input rule, so the two cannot disagree.

⚠️ Unknown still means push. A missed message is worse than a redundant one.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterable

#: How long a reported source is believed without a refresh. The ROAM app
#: re-posts while it is foregrounded; if it is killed, presence lapses.
DEFAULT_TTL_S = 60.0

@dataclass(frozen=True)
class PresenceSource:
    id: str
    kind: str
    panes: tuple[str, ...] = ()
    #: This source sees everything -- e.g. the panel itself is open in front of
    #: him. Suppresses every channel, not just some panes.
    covers_all: bool = False
    since: float = 0.0
    last_seen: float = 0.0
    ttl_s: float = DEFAULT_TTL_S
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def expires_at(self) -> float:
        return self.last_seen + self.ttl_s

    def is_live(self, now: float) -> bool:
        return now < self.expires_at

    def to_dict(self, now: float | None = None) -> dict[str, Any]:
        now = time.time() if now is None else now
        return {
            "id": self.id,
            "kind": self.kind,
            "panes": list(self.panes),
            "covers_all": self.covers_all,
            "since": self.since,
            "last_seen": self.last_seen,
            "idle_s": round(max(0.0, now - self.last_seen), 1),
            "expires_in_s": round(max(0.0, self.expires_at - now), 1),
            "detail": self.detail,
        }


class Presence:
    """The live set of presence sources. Ephemeral: a restart forgets, which
    fails towards notifying rather than towards silence."""

    def __init__(self, clock=None) -> None:
        self._clock = clock or time.time
        self._sources: dict[str, PresenceSource] = {}

    # ------------------------------------------------------------ writing

    def report(
        self,
        source_id: str,
        kind: str = "reported",
        panes: Iterable[str] = (),
        covers_all: bool = False,
        ttl_s: float = DEFAULT_TTL_S,
        detail: dict[str, Any] | None = None,
        now: float | None = None,
    ) -> PresenceSource:
        """Register or refresh a source. `since` survives a refresh."""
        if not source_id:
            raise ValueError("a presence source needs an id")
        now = self._clock() if now is None else now
        existing = self._sources.get(source_id)
        since = existing.since if existing and existing.is_live(now) else now
        source = PresenceSource(
            id=source_id,
            kind=kind,
            panes=tuple(panes),
            covers_all=bool(covers_all),
            since=since,
            last_seen=now,
            ttl_s=max(1.0, float(ttl_s)),
            detail=detail or {},
        )
        self._sources[source_id] = source
        return source

    def forget(self, source_id: str) -> bool:
        """Explicit departure -- the app backgrounding, a client detaching."""
        return self._sources.pop(source_id, None) is not None

    def sweep(self, now: float | None = None) -> list[str]:
        now = self._clock() if now is None else now
        expired = [i for i, s in self._sources.items() if not s.is_live(now)]
        for source_id in expired:
            del self._sources[source_id]
        return expired

    # ------------------------------------------------------------ reading

    def live(self, now: float | None = None) -> list[PresenceSource]:
        now = self._clock() if now is None else now
        return sorted(
            (s for s in self._sources.values() if s.is_live(now)),
            key=lambda s: (-s.last_seen, s.id),
        )

    def covered_panes(self, now: float | None = None) -> set[str]:
        return {pane for source in self.live(now) for pane in source.panes}

    def covers_everything(self, now: float | None = None) -> bool:
        return any(s.covers_all for s in self.live(now))

    def covers(self, pane_id: str, now: float | None = None) -> PresenceSource | None:
        """The source that means "he can already see this", if any."""
        for source in self.live(now):
            if source.covers_all or pane_id in source.panes:
                return source
        return None

    def should_push(self, pane_id: str, now: float | None = None) -> bool:
        """⚠️ Unknown means push. Absence of evidence is not presence."""
        return self.covers(pane_id, now) is None

    def snapshot(self, now: float | None = None) -> dict[str, Any]:
        now = self._clock() if now is None else now
        sources = self.live(now)
        return {
            "present": bool(sources),
            "covers_all": any(s.covers_all for s in sources),
            "covered_panes": sorted({p for s in sources for p in s.panes}),
            "sources": [s.to_dict(now) for s in sources],
            "server_time": now,
        }

    def signature(self, now: float | None = None) -> tuple:
        """What must change before the hub re-broadcasts presence.

        Deliberately excludes timestamps: a client typing continuously would
        otherwise emit a frame every poll and turn presence into a firehose.
        """
        return tuple(
            (s.id, s.kind, s.panes, s.covers_all) for s in self.live(now)
        )

#: What to record on an event when nobody can say where the conversation is --
#: a fresh pane, a store used without a hub, a lookup that failed. Notifies,
#: because unknown means push.
UNKNOWN_COVERAGE: dict[str, Any] = {"known": False, "covered": False, "by": []}
