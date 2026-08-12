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
from typing import Any, Iterable, Sequence

from transcript import MAX_BODY_CHARS, cap_body, summarise

DEFAULT_DB_PATH = Path(__file__).with_name("hub.sqlite")

SCHEMA_VERSION = 2


class EventKind(str, Enum):
    """Every kind of thing that can land in a channel thread.

    Clients must render unknown kinds gracefully -- this list will grow.
    """

    SENT = "sent"        # the wearer sent this text to the channel
    RECEIPT = "receipt"  # the agent acknowledged a prompt was submitted
    OUTCOME = "outcome"  # the agent finished a response
    OPENED = "opened"    # the pane appeared on this host
    CLOSED = "closed"    # the pane went away (channel is dead)
    NOTE = "note"        # free-form hub/agent note
    ERROR = "error"      # something failed on the way to the pane


ALL_KINDS = tuple(k.value for k in EventKind)


@dataclass(frozen=True)
class Event:
    id: int
    pane_id: str
    kind: str
    body: str
    #: Short, speakable, glanceable form of `body`. Always present; the client
    #: shows this on the strip and speaks it, and shows `body` in the thread.
    summary: str = ""
    meta: dict[str, Any] = field(default_factory=dict)
    ts: float = 0.0
    archived: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "pane_id": self.pane_id,
            "kind": self.kind,
            "body": self.body,
            "summary": self.summary,
            "meta": self.meta,
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "pane_id": self.pane_id,
            "label": self.label,
            "session": self.session,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "archived": self.archived,
        }


def _row_to_event(row: sqlite3.Row) -> Event:
    raw_meta = row["meta"]
    return Event(
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
    )


class Store:
    """SQLite-backed event log. Safe to share across threads."""

    def __init__(self, path: str | Path = DEFAULT_DB_PATH) -> None:
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
                ts       REAL    NOT NULL,
                archived INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS events_pane_idx ON events(pane_id, id);

            CREATE TABLE IF NOT EXISTS channels (
                pane_id    TEXT PRIMARY KEY,
                label      TEXT NOT NULL DEFAULT '',
                session    TEXT NOT NULL DEFAULT '',
                first_seen REAL NOT NULL,
                last_seen  REAL NOT NULL,
                archived   INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS schema_meta (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        # v1 -> v2: events gained `summary`. Existing rows are backfilled so a
        # client never meets an event without one.
        columns = {r["name"] for r in self._db.execute("PRAGMA table_info(events)")}
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
        payload = json.dumps(meta) if meta else None
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO events(pane_id, kind, body, summary, meta, ts) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                (pane_id, kind_value, body, summary, payload, stamp),
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
            ts=stamp,
            archived=False,
        )

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
