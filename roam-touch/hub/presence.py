"""Where the user is, so the hub can decide whether his arm needs to buzz.

The rule the whole thing serves: **push to the arm only when he is not
demonstrably already looking at the message.** That started as "don't notify
about the tmux pane he is typing in" and generalises here into presence with
named sources, because the Android client will want to say "I am foregrounded,
stop notifying me" and that must not be a special case bolted on afterwards.

A *source* is one piece of evidence that he is somewhere:

* **observed** -- the hub works it out. Today that is tmux: a client that has
  taken input recently, covering the pane on its screen.
* **reported** -- something tells the hub over `POST /presence`. The ROAM app
  reporting foreground is the reason this exists; it covers *everything*,
  because the panel already shows what a notification would say.

Every source carries a TTL and is refreshed by whoever owns it. That is the
extension point: a new source needs no new logic here, just a POST. Coverage is
the union across live sources.

## Decisions worth keeping

* ⚠️ **No signal means push.** A missed message is worse than a redundant one,
  so an empty registry is not "he must be here somewhere" -- it is "we do not
  know, so tell him". `should_push()` returns True for an unknown pane.
* ⚠️ **Only signals talos can actually observe.** macOS window focus and
  "is he in the room" are not observable from here and are deliberately absent.
  `HIDIdleTime` was tested and rejected: it read 13.2 hours idle while he was
  actively typing, because he works over SSH and it measures *this* machine's
  keyboard, not his.
* A source that says nothing about panes (`panes=()`, `covers_all=False`) is
  still presence -- it shows up in `/presence` and on the panel -- but it
  suppresses nothing. Evidence he is at a keyboard somewhere is not evidence he
  can see a given channel.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterable

#: How long a reported source is believed without a refresh. The ROAM app
#: re-posts while it is foregrounded; if it is killed, presence lapses.
DEFAULT_TTL_S = 60.0

#: Ids the hub owns. A reported source may not claim one, or a client could
#: overwrite (or forge) an observed fact.
OBSERVED_PREFIXES: tuple[str, ...] = ("tmux:",)


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
