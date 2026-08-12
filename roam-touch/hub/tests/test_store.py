"""The store is the hub's memory. If it loses an outcome, the wearer never
learns the job finished -- so these cover ordering, catch-up, restart survival
and the no-hard-delete rule, not just "a row went in"."""

from __future__ import annotations

import sqlite3
import threading

import pytest

from store import Event, EventKind, Store
from transcript import MAX_BODY_CHARS


def test_append_returns_event_with_monotonic_ids(store: Store):
    a = store.append("%0", EventKind.SENT, "hello")
    b = store.append("%0", EventKind.RECEIPT, "")
    c = store.append("%1", EventKind.SENT, "other channel")
    assert (a.id, b.id, c.id) == (1, 2, 3)
    assert a.kind == "sent" and a.body == "hello" and a.ts > 0


def test_kind_accepts_plain_strings_from_hooks(store: Store):
    event = store.append("%0", "outcome", "done")
    assert event.kind == "outcome"


def test_append_requires_pane_and_kind(store: Store):
    with pytest.raises(ValueError):
        store.append("", EventKind.SENT, "x")
    with pytest.raises(ValueError):
        store.append("%0", "", "x")


def test_history_is_per_channel_and_oldest_first(store: Store):
    store.append("%0", EventKind.SENT, "one")
    store.append("%1", EventKind.SENT, "not mine")
    store.append("%0", EventKind.OUTCOME, "two")
    bodies = [e.body for e in store.history("%0")]
    assert bodies == ["one", "two"]


def test_history_limit_keeps_the_most_recent_still_in_order(store: Store):
    for i in range(10):
        store.append("%0", EventKind.NOTE, f"n{i}")
    recent = store.history("%0", limit=3)
    assert [e.body for e in recent] == ["n7", "n8", "n9"]


def test_history_since_is_exclusive(store: Store):
    first = store.append("%0", EventKind.SENT, "one")
    second = store.append("%0", EventKind.OUTCOME, "two")
    assert [e.id for e in store.history("%0", since=first.id)] == [second.id]
    assert store.history("%0", since=second.id) == []


def test_events_since_spans_channels_for_websocket_catchup(store: Store):
    store.append("%0", EventKind.SENT, "a")
    mark = store.latest_event_id()
    store.append("%1", EventKind.OUTCOME, "b")
    store.append("%0", EventKind.OUTCOME, "c")
    caught_up = store.events_since(mark)
    assert [(e.pane_id, e.body) for e in caught_up] == [("%1", "b"), ("%0", "c")]


def test_meta_round_trips_as_json(store: Store):
    event = store.append("%0", EventKind.OUTCOME, "done", meta={"ms": 1234, "ok": True})
    stored = store.history("%0")[-1]
    assert stored.meta == {"ms": 1234, "ok": True}
    assert event.meta == stored.meta


def test_body_with_control_words_is_stored_verbatim(store: Store):
    """A transcript can contain the word Enter or C-c. Nothing may mangle it."""
    body = "run C-c then press Enter twice -- and 'quote' \"me\""
    store.append("%0", EventKind.SENT, body)
    assert store.history("%0")[-1].body == body


def test_every_event_carries_a_speakable_summary(store: Store):
    """The panel shows and Piper speaks `summary`; `body` keeps everything."""
    body = "## Result\n\nAll **green**.\n\n```bash\nnpm test\n```\n"
    event = store.append("%0", EventKind.OUTCOME, body)
    assert event.body == body, "the full answer is never lost"
    assert event.summary == "Result All green. [code, 1 line]"
    assert store.history("%0")[-1].summary == event.summary


def test_an_explicit_summary_is_kept(store: Store):
    event = store.append("%0", EventKind.OUTCOME, "long thing", summary="short thing")
    assert event.summary == "short thing"


def test_a_giant_answer_is_capped_and_the_original_size_recorded(store: Store):
    huge = "z" * (MAX_BODY_CHARS + 5000)
    event = store.append("%0", EventKind.OUTCOME, huge)
    assert len(event.body) == MAX_BODY_CHARS
    assert event.body.endswith("… [truncated]")
    assert event.meta["truncated_from"] == MAX_BODY_CHARS + 5000
    assert store.history("%0")[-1].body == event.body


def test_capping_preserves_other_meta(store: Store):
    event = store.append(
        "%0", EventKind.OUTCOME, "z" * (MAX_BODY_CHARS + 1), meta={"source": "hook"}
    )
    assert event.meta["source"] == "hook"
    assert "truncated_from" in event.meta


def test_a_v1_database_gains_summaries_on_open(tmp_path):
    """The live DB predates `summary`; opening it must migrate, not explode."""
    path = tmp_path / "old.sqlite"
    db = sqlite3.connect(path)
    db.executescript(
        """
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, pane_id TEXT NOT NULL,
            kind TEXT NOT NULL, body TEXT NOT NULL DEFAULT '', meta TEXT,
            ts REAL NOT NULL, archived INTEGER NOT NULL DEFAULT 0);
        INSERT INTO events(pane_id, kind, body, ts)
            VALUES('%0', 'outcome', '**done** at last', 1.0);
        """
    )
    db.commit()
    db.close()
    with Store(path) as st:
        event = st.history("%0")[-1]
        assert event.body == "**done** at last"
        assert event.summary == "done at last", "existing rows are backfilled"
        st.append("%0", EventKind.NOTE, "after the migration")


def test_last_event_and_count(store: Store):
    assert store.last_event("%0") is None
    store.append("%0", EventKind.SENT, "a")
    store.append("%0", EventKind.OUTCOME, "b")
    assert store.last_event("%0").body == "b"
    assert store.event_count("%0") == 2


# ------------------------------------------------------------ no hard delete


def test_archive_history_is_a_soft_delete(store: Store):
    store.append("%0", EventKind.SENT, "keep me")
    store.append("%0", EventKind.OUTCOME, "me too")
    assert store.archive_history("%0") == 2
    assert store.history("%0") == []
    assert store.event_count("%0") == 0
    recovered = store.history("%0", include_archived=True)
    assert [e.body for e in recovered] == ["keep me", "me too"]
    assert all(e.archived for e in recovered)


def test_archived_history_can_be_restored(store: Store):
    store.append("%0", EventKind.SENT, "hello")
    store.archive_history("%0")
    assert store.restore_history("%0") == 1
    assert [e.body for e in store.history("%0")] == ["hello"]


def test_archived_events_are_skipped_by_catchup(store: Store):
    store.append("%0", EventKind.SENT, "gone")
    store.archive_history("%0")
    store.append("%0", EventKind.OUTCOME, "here")
    assert [e.body for e in store.events_since(0)] == ["here"]


def test_archiving_a_channel_keeps_its_history(store: Store):
    store.remember_channel("%0", "a channel", "main")
    store.append("%0", EventKind.SENT, "history survives")
    assert store.set_channel_archived("%0", True) is True
    assert store.known_channels() == []
    assert [c.pane_id for c in store.known_channels(include_archived=True)] == ["%0"]
    assert [e.body for e in store.history("%0")] == ["history survives"]
    store.set_channel_archived("%0", False)
    assert [c.pane_id for c in store.known_channels()] == ["%0"]


def test_store_refuses_to_hard_delete(store: Store):
    with pytest.raises(NotImplementedError):
        store.prune_placeholder(["%0"])


# ---------------------------------------------------------------- channels


def test_remember_channel_upserts_and_keeps_first_seen(store: Store):
    first = store.remember_channel("%0", "old title", "main", ts=100.0)
    later = store.remember_channel("%0", "new title", "main", ts=200.0)
    assert first.first_seen == 100.0
    assert later.first_seen == 100.0, "first_seen must survive a retitle"
    assert later.last_seen == 200.0
    assert later.label == "new title"
    assert len(store.known_channels()) == 1


def test_known_channels_sorted_by_last_seen(store: Store):
    store.remember_channel("%0", "older", "main", ts=100.0)
    store.remember_channel("%1", "newer", "aug", ts=200.0)
    assert [c.pane_id for c in store.known_channels()] == ["%1", "%0"]


def test_get_channel_missing_is_none(store: Store):
    assert store.get_channel("%9") is None
    assert store.set_channel_archived("%9", True) is False


# ----------------------------------------------------------------- durability


def test_history_survives_a_restart(tmp_path):
    path = tmp_path / "hub.sqlite"
    with Store(path) as st:
        st.remember_channel("%0", "before restart", "main")
        st.append("%0", EventKind.OUTCOME, "landed while the lid was shut")
    with Store(path) as st:
        assert [e.body for e in st.history("%0")] == ["landed while the lid was shut"]
        assert st.get_channel("%0").label == "before restart"
        assert st.latest_event_id() == 1
        assert st.append("%0", EventKind.SENT, "next").id == 2, "ids never reused"


def test_concurrent_writers_do_not_lose_events(store: Store):
    """FastAPI runs sync work in a threadpool; the store is shared."""

    def writer(pane: str) -> None:
        for i in range(50):
            store.append(pane, EventKind.NOTE, f"{pane}-{i}")

    threads = [threading.Thread(target=writer, args=(f"%{n}",)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert store.latest_event_id() == 200
    for n in range(4):
        assert store.event_count(f"%{n}") == 50
