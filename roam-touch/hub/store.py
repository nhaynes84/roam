"""Durable per-channel event history for the ROAM Touch hub.

The hub holds the state; the panel is only a view. An outcome can land minutes
after the prompt was sent, while the wearer is looking at a different channel or
has the lid closed entirely -- so every message, receipt and outcome is written
here first and pushed second. A client that was asleep catches up by asking for
everything after the last event id it saw.

Keying
------
Events are keyed on the tmux **pane id** (`%3`). Pane ids are stable for the
life of a pane and are never reused, so a stored thread can never silently
re-point at a different pane. See `channels.py`.

Deletion
--------
Nothing is ever hard-deleted. "Clearing" a thread sets `archived = 1` on its
events; "removing" a dead channel sets `archived = 1` on the channel row. Both
remain readable with `include_archived=True`.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from presence import UNKNOWN_COVERAGE
from transcript import MAX_BODY_CHARS, cap_body, summarise

DEFAULT_DB_PATH = Path(__file__).with_name("hub.sqlite")

SCHEMA_VERSION = 6

#: Where a channel's last inbound message came from. This is the whole
#: notification rule: **reply where the last message came from.**
INPUT_TMUX = "tmux"  # he typed it at the keyboard; the answer stays there
INPUT_APP = "app"    # it came in over the API from ROAM; the answer goes there

#: Where a `notice` goes when whatever sent it has no pane to claim -- an agent
#: under launchd or cron, a script run over ssh. It is not a tmux pane id and
#: never can be (tmux ids are `%<n>`), so it cannot collide with a real
#: channel, and it is a single exact literal rather than a widened rule.
#:
#: The alternative was to borrow some pane's channel, which files a message
#: under a conversation that did not send it and would inherit that
#: conversation's coverage -- silence for a message nobody was watching for.
HOST_CHANNEL_ID = "@host"


class EventKind(str, Enum):
    """Every kind of thing that can land in a channel thread.

    Clients must render unknown kinds gracefully -- this list will grow.
    """

    SENT = "sent"        # the wearer sent this text to the channel
    RECEIPT = "receipt"  # the agent acknowledged a prompt was submitted
    OUTCOME = "outcome"  # the agent finished a response
    OPENED = "opened"    # the pane appeared on this host
    CLOSED = "closed"    # the pane went away (channel is dead)
    CONTROL = "control"  # a control key was sent (escape, interrupt)
    NOTE = "note"        # free-form hub/agent note
    #: A tool saying something to the wearer -- `roam-msg "build finished"`.
    #: Not part of the conversation: it never makes a channel owe an answer and
    #: never moves `last_input_source`. It is pushed like an outcome, and
    #: suppressed by exactly the same coverage rule.
    NOTICE = "notice"
    ERROR = "error"      # something failed on the way to the pane


ALL_KINDS = tuple(k.value for k in EventKind)


@dataclass(frozen=True)
class Event:
    id: int
    pane_id: str
    kind: str
    body: str
    #: Short, speakable, glanceable form of `body`. Always present; the client
    #: shows this on the strip and speaks it, and shows `body` when expanded.
    summary: str = ""
    meta: dict[str, Any] = field(default_factory=dict)
    ts: float = 0.0
    archived: bool = False
    #: ⚠️ This event was written straight to the ledger because the hub was
    #: not running, so it never went through the push path. Transient: the hub
    #: adopts it (`claim_pending`) the moment it is up and the flag clears. In
    #: steady state nothing is pending -- it is a fault signal, not a history.
    pending: bool = False
    #: Was he already looking at this channel **when this landed**? Frozen at
    #: creation, because by the time a sleeping phone reconnects, live presence
    #: answers a different question. Governs notification only -- never whether
    #: the event is stored, returned, or shown in the thread.
    coverage: dict[str, Any] = field(default_factory=lambda: dict(UNKNOWN_COVERAGE))

    def to_dict(self, inline_limit: int | None = None) -> dict[str, Any]:
        """Summary always; body in full unless this is a bulk payload.

        `inline_limit` trims the body carried inside a list or stream frame.
        The event is never stored that way and `GET /events/{id}` always
        returns it whole -- the client expands, it does not lose.
        """
        body = self.body
        truncated = False
        if inline_limit is not None and len(body) > inline_limit:
            body = body[:inline_limit]
            truncated = True
        return {
            "id": self.id,
            "pane_id": self.pane_id,
            "kind": self.kind,
            "summary": self.summary,
            "body": body,
            "body_chars": len(self.body),
            "body_truncated": truncated,
            "meta": self.meta,
            "coverage": self.coverage,
            "ts": self.ts,
            "archived": self.archived,
        }


@dataclass(frozen=True)
class StoredChannel:
    """What the hub remembers about a pane, including panes that are gone."""

    pane_id: str
    label: str
    session: str
    first_seen: float
    last_seen: float
    archived: bool = False
    #: When this pane's visible output last changed. The liveness heartbeat:
    #: "working" and "hung" look identical without it.
    last_output_at: float | None = None
    #: Where this channel's last inbound message came from -- `tmux` or `app`.
    #: None until something arrives; unknown means notify.
    last_input_source: str | None = None
    last_input_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "pane_id": self.pane_id,
            "label": self.label,
            "session": self.session,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "archived": self.archived,
            "last_output_at": self.last_output_at,
            "last_input_source": self.last_input_source,
            "last_input_at": self.last_input_at,
        }


def _row_to_event(row: sqlite3.Row) -> Event:
    raw_meta = row["meta"]
    raw_coverage = row["coverage"]
    keys = row.keys()
    return Event(
        pending=bool(row["pending"]) if "pending" in keys else False,
        coverage=json.loads(raw_coverage) if raw_coverage else dict(UNKNOWN_COVERAGE),
        id=row["id"],
        pane_id=row["pane_id"],
        kind=row["kind"],
        body=row["body"],
        summary=row["summary"] or "",
        meta=json.loads(raw_meta) if raw_meta else {},
        ts=row["ts"],
        archived=bool(row["archived"]),
    )


def _row_to_channel(row: sqlite3.Row) -> StoredChannel:
    return StoredChannel(
        pane_id=row["pane_id"],
        label=row["label"],
        session=row["session"],
        first_seen=row["first_seen"],
        last_seen=row["last_seen"],
        archived=bool(row["archived"]),
        last_output_at=row["last_output_at"],
        last_input_source=row["last_input_source"],
        last_input_at=row["last_input_at"],
    )


class Store:
    """SQLite-backed event log. Safe to share across threads."""

    def __init__(
        self,
        path: str | Path = DEFAULT_DB_PATH,
        coverage_provider: Callable[[str], dict[str, Any]] | None = None,
    ) -> None:
        #: Asked "was he covered on this pane right now?" for every event, so
        #: no call site can forget to stamp one. The hub points this at its
        #: `Presence`; without one, every event records "unknown", which
        #: notifies.
        self.coverage_provider = coverage_provider
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(self.path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=NORMAL")
            self._db.execute("PRAGMA foreign_keys=ON")
            self._migrate()

    # ---------------------------------------------------------------- schema

    def _migrate(self) -> None:
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                pane_id  TEXT    NOT NULL,
                kind     TEXT    NOT NULL,
                body     TEXT    NOT NULL DEFAULT '',
                summary  TEXT    NOT NULL DEFAULT '',
                meta     TEXT,
                coverage TEXT,
                ts       REAL    NOT NULL,
                archived INTEGER NOT NULL DEFAULT 0,
                pending  INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS events_pane_idx ON events(pane_id, id);

            CREATE TABLE IF NOT EXISTS channels (
                pane_id        TEXT PRIMARY KEY,
                label          TEXT NOT NULL DEFAULT '',
                session        TEXT NOT NULL DEFAULT '',
                first_seen     REAL NOT NULL,
                last_seen      REAL NOT NULL,
                archived       INTEGER NOT NULL DEFAULT 0,
                last_output_at REAL,
                last_input_source TEXT,
                last_input_at  REAL
            );

            CREATE TABLE IF NOT EXISTS schema_meta (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        # v2 -> v3: channels gained the liveness heartbeat. Unknown until the
        # poller next sees output, which is honest -- NULL means "don't know",
        # not "idle forever".
        channel_columns = {
            r["name"] for r in self._db.execute("PRAGMA table_info(channels)")
        }
        if "last_output_at" not in channel_columns:
            self._db.execute("ALTER TABLE channels ADD COLUMN last_output_at REAL")
        # v4 -> v5: channels remember where their last message came from. NULL
        # on existing rows means "unknown", which notifies.
        if "last_input_source" not in channel_columns:
            self._db.execute("ALTER TABLE channels ADD COLUMN last_input_source TEXT")
            self._db.execute("ALTER TABLE channels ADD COLUMN last_input_at REAL")

        columns = {r["name"] for r in self._db.execute("PRAGMA table_info(events)")}

        # v5 -> v6: events gained `pending` -- written straight to the ledger
        # while the hub process was down, so never pushed. Existing rows are 0:
        # they went through the hub, which is exactly what "not pending" means.
        if "pending" not in columns:
            self._db.execute(
                "ALTER TABLE events ADD COLUMN pending INTEGER NOT NULL DEFAULT 0"
            )
            columns.add("pending")

        # v3 -> v4: events gained `coverage`. Existing rows stay NULL, which
        # reads back as "unknown" -- so anything replayed from before this
        # existed notifies rather than being silently swallowed.
        if "coverage" not in columns:
            self._db.execute("ALTER TABLE events ADD COLUMN coverage TEXT")
            columns.add("coverage")

        # v1 -> v2: events gained `summary`. Existing rows are backfilled so a
        # client never meets an event without one.
        if "summary" not in columns:
            self._db.execute(
                "ALTER TABLE events ADD COLUMN summary TEXT NOT NULL DEFAULT ''"
            )
            rows = self._db.execute(
                "SELECT id, body FROM events WHERE body != ''"
            ).fetchall()
            self._db.executemany(
                "UPDATE events SET summary = ? WHERE id = ?",
                [(summarise(r["body"]), r["id"]) for r in rows],
            )
        self._db.execute(
            "INSERT INTO schema_meta(key, value) VALUES('version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(SCHEMA_VERSION),),
        )
        self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---------------------------------------------------------------- events

    def append(
        self,
        pane_id: str,
        kind: str | EventKind,
        body: str = "",
        meta: dict[str, Any] | None = None,
        ts: float | None = None,
        summary: str | None = None,
        coverage: dict[str, Any] | None = None,
        pending: bool = False,
    ) -> Event:
        """Write one event and return it, with its assigned id.

        The size rail and the summary live here rather than in the callers, so
        nothing -- hook, client or poller -- can put an unbounded blob or an
        unsummarised body into the log. `meta.truncated_from` records the
        original length whenever the body was cut.
        """
        if not pane_id:
            raise ValueError("pane_id is required")
        kind_value = kind.value if isinstance(kind, EventKind) else str(kind)
        if not kind_value:
            raise ValueError("kind is required")
        stamp = time.time() if ts is None else float(ts)
        body, original_length = cap_body(body or "", MAX_BODY_CHARS)
        if original_length is not None:
            meta = {**(meta or {}), "truncated_from": original_length}
        if summary is None:
            summary = summarise(body)
        if coverage is None:
            coverage = self._coverage_for(pane_id)
        payload = json.dumps(meta) if meta else None
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO events"
                "(pane_id, kind, body, summary, meta, coverage, ts, pending) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    pane_id,
                    kind_value,
                    body,
                    summary,
                    payload,
                    json.dumps(coverage),
                    stamp,
                    1 if pending else 0,
                ),
            )
            self._db.commit()
            event_id = int(cur.lastrowid)
        return Event(
            id=event_id,
            pane_id=pane_id,
            kind=kind_value,
            body=body,
            summary=summary,
            meta=meta or {},
            coverage=coverage,
            ts=stamp,
            archived=False,
            pending=pending,
        )

    def _coverage_for(self, pane_id: str) -> dict[str, Any]:
        """Never let a broken provider stop an event being written -- and when
        it breaks, record "unknown", which errs towards notifying."""
        if self.coverage_provider is None:
            return dict(UNKNOWN_COVERAGE)
        try:
            stamped = self.coverage_provider(pane_id)
        except Exception:
            return dict(UNKNOWN_COVERAGE)
        return stamped if isinstance(stamped, dict) else dict(UNKNOWN_COVERAGE)

    def history(
        self,
        pane_id: str,
        limit: int = 200,
        since: int | None = None,
        include_archived: bool = False,
    ) -> list[Event]:
        """One channel's thread, oldest first.

        `since` is an exclusive event id -- pass the highest id you already
        have. Without it you get the most recent `limit` events (still ordered
        oldest first, so the panel can append them in order).
        """
        clauses = ["pane_id = ?"]
        params: list[Any] = [pane_id]
        if not include_archived:
            clauses.append("archived = 0")
        if since is not None:
            clauses.append("id > ?")
            params.append(int(since))
        where = " AND ".join(clauses)
        params.append(max(0, int(limit)))
        with self._lock:
            rows = self._db.execute(
                f"SELECT * FROM events WHERE {where} ORDER BY id DESC LIMIT ?",
                params,
            ).fetchall()
        return [_row_to_event(r) for r in reversed(rows)]

    def events_since(self, since: int, limit: int = 500) -> list[Event]:
        """Every non-archived event after `since`, across all channels."""
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM events WHERE id > ? AND archived = 0 "
                "ORDER BY id ASC LIMIT ?",
                (int(since), max(0, int(limit))),
            ).fetchall()
        return [_row_to_event(r) for r in rows]

    def latest_event_id(self) -> int:
        with self._lock:
            row = self._db.execute("SELECT MAX(id) AS m FROM events").fetchone()
        return int(row["m"] or 0)

    def get_event(self, event_id: int) -> Event | None:
        """One event, whole -- what "expand the details" fetches."""
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM events WHERE id = ?", (int(event_id),)
            ).fetchone()
        return _row_to_event(row) if row else None

    def last_event(self, pane_id: str) -> Event | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM events WHERE pane_id = ? AND archived = 0 "
                "ORDER BY id DESC LIMIT 1",
                (pane_id,),
            ).fetchone()
        return _row_to_event(row) if row else None

    def event_count(self, pane_id: str, include_archived: bool = False) -> int:
        sql = "SELECT COUNT(*) AS n FROM events WHERE pane_id = ?"
        if not include_archived:
            sql += " AND archived = 0"
        with self._lock:
            row = self._db.execute(sql, (pane_id,)).fetchone()
        return int(row["n"])

    # ------------------------------------------------- the offline path

    def pending_count(self) -> int:
        """How many events never reached the push path.

        Nonzero means the hub was not running when something tried to tell him
        about it. `GET /status` reports it and `roam-msg` says it on its next
        successful call: a count nobody reads is the same failure as the
        dead-letter file this replaced.
        """
        with self._lock:
            row = self._db.execute(
                "SELECT COUNT(*) AS n FROM events WHERE pending = 1"
            ).fetchone()
        return int(row["n"])

    def claim_pending(self, limit: int = 100) -> list[Event]:
        """Take the events written while the hub was down, once.

        Read and clear in one transaction, so an event cannot be adopted twice
        and buzz twice. The rows stay exactly where they are -- only the flag
        moves, which is why this is a column and not a queue table.
        """
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM events WHERE pending = 1 ORDER BY id ASC LIMIT ?",
                (max(0, int(limit)),),
            ).fetchall()
            if not rows:
                return []
            ids = [int(r["id"]) for r in rows]
            self._db.execute(
                "UPDATE events SET pending = 0 WHERE id IN "
                f"({','.join('?' * len(ids))})",
                ids,
            )
            self._db.commit()
        return [_row_to_event(r) for r in rows]

    def archive_history(self, pane_id: str) -> int:
        """Soft-clear a thread. Rows stay; they just stop being served."""
        with self._lock:
            cur = self._db.execute(
                "UPDATE events SET archived = 1 WHERE pane_id = ? AND archived = 0",
                (pane_id,),
            )
            self._db.commit()
            return int(cur.rowcount)

    def restore_history(self, pane_id: str) -> int:
        with self._lock:
            cur = self._db.execute(
                "UPDATE events SET archived = 0 WHERE pane_id = ? AND archived = 1",
                (pane_id,),
            )
            self._db.commit()
            return int(cur.rowcount)

    # -------------------------------------------------------------- channels

    def remember_channel(
        self,
        pane_id: str,
        label: str = "",
        session: str = "",
        ts: float | None = None,
    ) -> StoredChannel:
        """Record that a pane exists (or existed). Idempotent.

        `first_seen` is preserved across updates; `label` and `session` track
        the live pane, because a Claude pane retitles itself as the session
        summary changes and the panel shows that title as the channel name.
        """
        stamp = time.time() if ts is None else float(ts)
        with self._lock:
            self._db.execute(
                "INSERT INTO channels(pane_id, label, session, first_seen, last_seen) "
                "VALUES(?, ?, ?, ?, ?) "
                "ON CONFLICT(pane_id) DO UPDATE SET "
                "  label = excluded.label, "
                "  session = excluded.session, "
                "  last_seen = excluded.last_seen",
                (pane_id, label, session, stamp, stamp),
            )
            self._db.commit()
            row = self._db.execute(
                "SELECT * FROM channels WHERE pane_id = ?", (pane_id,)
            ).fetchone()
        return _row_to_channel(row)

    def set_channel_activity(self, pane_id: str, ts: float) -> None:
        """Record that this pane's visible output changed at `ts`."""
        with self._lock:
            self._db.execute(
                "UPDATE channels SET last_output_at = ? WHERE pane_id = ?",
                (float(ts), pane_id),
            )
            self._db.commit()

    def set_channel_input(
        self, pane_id: str, source: str, ts: float | None = None
    ) -> None:
        """Record where this channel's latest inbound message came from.

        ★ The notification rule in one line: **reply where the last message
        came from.** He typed the prompt in tmux, so the answer belongs in
        tmux; he sent it from ROAM, so the answer belongs on ROAM. Switching
        is just sending from the other place -- exactly like any messaging app,
        and nothing has to infer where he is.

        Durable on purpose: a hub restart must not turn a tmux conversation
        into a phone conversation. There is deliberately **no expiry** -- a
        stale answer still belongs to the conversation that asked for it.
        """
        stamp = time.time() if ts is None else float(ts)
        with self._lock:
            self._db.execute(
                "UPDATE channels SET last_input_source = ?, last_input_at = ? "
                "WHERE pane_id = ?",
                (source, stamp, pane_id),
            )
            self._db.commit()

    def get_channel(self, pane_id: str) -> StoredChannel | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM channels WHERE pane_id = ?", (pane_id,)
            ).fetchone()
        return _row_to_channel(row) if row else None

    def known_channels(self, include_archived: bool = False) -> list[StoredChannel]:
        sql = "SELECT * FROM channels"
        if not include_archived:
            sql += " WHERE archived = 0"
        sql += " ORDER BY last_seen DESC"
        with self._lock:
            rows = self._db.execute(sql).fetchall()
        return [_row_to_channel(r) for r in rows]

    def set_channel_archived(self, pane_id: str, archived: bool) -> bool:
        """Hide (or unhide) a channel. Never deletes it or its history."""
        with self._lock:
            cur = self._db.execute(
                "UPDATE channels SET archived = ? WHERE pane_id = ?",
                (1 if archived else 0, pane_id),
            )
            self._db.commit()
            return cur.rowcount > 0

    def prune_placeholder(self, pane_ids: Sequence[str]) -> None:  # pragma: no cover
        """Deliberately absent: the hub never hard-deletes. Kept as a marker."""
        raise NotImplementedError("the hub never hard-deletes; use archive_*")


def bulk_remember(store: Store, channels: Iterable[Any]) -> None:
    """Record a batch of live `channels.Channel` objects."""
    for ch in channels:
        store.remember_channel(ch.pane_id, ch.label, ch.session)
