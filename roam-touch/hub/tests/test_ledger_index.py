"""Turning the ledger and the session transcripts into index chunks.

The rules that matter: never index a credential, never write a second parser
for the transcript schema, and give a result enough context to be useful read
aloud -- which channel, when, and what was said.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import pytest

import ledger_index as li
from store import EventKind, Store


@pytest.fixture
def ledger(tmp_path) -> Path:
    path = tmp_path / "hub.sqlite"
    with Store(path) as st:
        st.remember_channel("%0", "✳ Augment things", "augment")
        st.append("%0", EventKind.SENT, "run the whole test suite please")
        st.append("%0", EventKind.OUTCOME, "The suite is green: 243 tests, no failures.")
        st.append("%0", EventKind.OPENED, "bookkeeping nobody searches for")
        st.append("%0", EventKind.RECEIPT, "")
    return path


# ------------------------------------------------------------------ ledger


def test_ledger_chunks_carry_channel_and_time(ledger):
    chunks = list(li.ledger_chunks(ledger))
    outcome = [c for c in chunks if "green" in c["text"]][0]
    assert "✳ Augment things" in outcome["text"], "which channel"
    assert "outcome on" in outcome["text"], "what kind of thing it was"
    assert time.strftime("%Y-%m-%d") in outcome["text"], "when"
    assert outcome["path"].startswith("ledger/")


def test_bookkeeping_kinds_are_not_indexed(ledger):
    texts = " ".join(c["text"] for c in li.ledger_chunks(ledger))
    assert "bookkeeping nobody searches" not in texts
    assert "opened" not in texts


def test_short_and_empty_events_are_skipped(ledger):
    ids = {c["id"] for c in li.ledger_chunks(ledger)}
    assert all(isinstance(i, str) and i.startswith("ledger-") for i in ids)
    assert len(ids) == 2, "only the two events with real text"


def test_archived_events_leave_the_index(tmp_path):
    """Soft-delete has to reach search: hidden in the thread but findable by
    `memsearch` is not hidden."""
    path = tmp_path / "hub.sqlite"
    with Store(path) as st:
        st.remember_channel("%0", "a channel", "main")
        st.append("%0", EventKind.OUTCOME, "a thing he later cleared from the thread")
        assert len(list(li.ledger_chunks(path))) == 1
        st.archive_history("%0")
    assert list(li.ledger_chunks(path)) == []


def test_an_archived_channels_events_leave_the_index(tmp_path):
    """Archiving a whole channel hides its events too -- how a test channel
    (or anything he removes) stops surfacing in search."""
    path = tmp_path / "hub.sqlite"
    with Store(path) as st:
        st.remember_channel("%9", "TEST throwaway", "probe")
        st.append("%9", EventKind.OUTCOME, "output from a test run, not real work")
        assert len(list(li.ledger_chunks(path))) == 1
        st.set_channel_archived("%9", True)
    assert list(li.ledger_chunks(path)) == []


def test_a_missing_ledger_is_not_an_error(tmp_path):
    assert list(li.ledger_chunks(tmp_path / "nope.sqlite")) == []


def test_chunk_ids_are_stable_so_reindexing_is_incremental(ledger):
    first = [c["id"] for c in li.ledger_chunks(ledger)]
    second = [c["id"] for c in li.ledger_chunks(ledger)]
    assert first == second and first


# ---------------------------------------------------------------- secrets


@pytest.mark.parametrize(
    "secret",
    [
        "here is the key sk-abcdefghijklmnop1234567890",
        "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345",
        "AKIAIOSFODNN7EXAMPLE",
        "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAK",
        "password: hunter2hunter2",
        "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig",
    ],
)
def test_credentials_are_never_indexed(secret):
    """An embedding is a copy and a search result is a disclosure."""
    assert li.looks_secret(secret) is True
    assert li.redactable(f"some context around it {secret} and more text here") is None


def test_ordinary_prose_is_not_mistaken_for_a_secret():
    text = "The deploy finished and all checks passed, so I merged it to main."
    assert li.looks_secret(text) is False
    assert li.redactable(text) == text


def test_a_ledger_event_containing_a_credential_is_dropped(tmp_path):
    path = tmp_path / "hub.sqlite"
    with Store(path) as st:
        st.remember_channel("%0", "a channel", "main")
        st.append("%0", EventKind.OUTCOME, "the token is ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345")
        st.append("%0", EventKind.OUTCOME, "this one is a perfectly ordinary sentence")
    texts = [c["text"] for c in li.ledger_chunks(path)]
    assert len(texts) == 1
    assert "ghp_" not in texts[0]


def test_secret_filenames_are_never_read(tmp_path):
    token = tmp_path / "hub-token.txt"
    token.write_text("a-real-looking-token-value", encoding="utf-8")
    assert list(li.session_chunks(token)) == []


def test_trivial_text_is_skipped():
    assert li.redactable("ok") is None
    assert li.redactable("") is None


# --------------------------------------------------------------- sessions


def write_session(path: Path, records: list[dict]) -> Path:
    path.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )
    return path


def assistant(msg_id: str, *blocks, sidechain=False) -> dict:
    return {
        "type": "assistant",
        "isSidechain": sidechain,
        "message": {"id": msg_id, "content": list(blocks)},
    }


def test_session_chunks_include_both_sides_of_the_conversation(tmp_path):
    path = write_session(
        tmp_path / "abcdef12-session.jsonl",
        [
            {
                "type": "user",
                "message": {"role": "user", "content": "why did the deploy fail last night"},
            },
            assistant(
                "m1",
                {"type": "thinking", "thinking": "internal reasoning nobody should search"},
                {"type": "text", "text": "It failed because the Node runtime was pinned wrong."},
            ),
        ],
    )
    chunks = list(li.session_chunks(path))
    joined = " ".join(c["text"] for c in chunks)
    assert "why did the deploy fail" in joined, "his question is searchable"
    assert "Node runtime was pinned wrong" in joined, "and the answer"
    assert "internal reasoning" not in joined, "thinking is not what was said"


def test_tool_calls_are_not_indexed(tmp_path):
    path = write_session(
        tmp_path / "s.jsonl",
        [assistant("m1", {"type": "tool_use", "id": "t", "name": "Bash", "input": {"command": "ls"}})],
    )
    assert list(li.session_chunks(path)) == []


def test_subagent_turns_are_not_indexed_as_the_session(tmp_path):
    path = write_session(
        tmp_path / "s.jsonl",
        [
            assistant("m1", {"type": "text", "text": "the main agent said this clearly"}),
            assistant("m2", {"type": "text", "text": "subagent chatter goes here"}, sidechain=True),
        ],
    )
    joined = " ".join(c["text"] for c in li.session_chunks(path))
    assert "main agent said this" in joined
    assert "subagent chatter" not in joined


def test_the_session_id_is_in_every_chunk(tmp_path):
    path = write_session(
        tmp_path / "deadbeef-1234.jsonl",
        [assistant("m1", {"type": "text", "text": "an answer long enough to index properly"})],
    )
    chunk = list(li.session_chunks(path))[0]
    assert "deadbeef" in chunk["text"]
    assert chunk["path"] == "sessions/deadbeef-1234.jsonl"


def test_a_credential_pasted_into_a_session_is_dropped(tmp_path):
    path = write_session(
        tmp_path / "s.jsonl",
        [assistant("m1", {"type": "text", "text": "the key is sk-abcdefghijklmnopqrst1234"})],
    )
    assert list(li.session_chunks(path)) == []


def test_a_missing_session_file_is_empty(tmp_path):
    assert list(li.session_chunks(tmp_path / "nope.jsonl")) == []


def test_session_sources_report_mtime_and_size_for_incremental_runs(tmp_path):
    write_session(tmp_path / "a.jsonl", [assistant("m1", {"type": "text", "text": "x" * 80})])
    found = list(li.session_sources(tmp_path))
    assert len(found) == 1
    path, mtime, size = found[0]
    assert path.name == "a.jsonl" and mtime > 0 and size > 0


def test_no_session_directory_is_not_an_error(tmp_path):
    assert list(li.session_sources(tmp_path / "missing")) == []
    assert list(li.all_session_chunks(tmp_path / "missing")) == []


# ------------------------------------------------ one parser, not two


def test_the_transcript_parser_is_reused_not_reimplemented():
    """The Stop hook and the indexer must never disagree about this schema."""
    import transcript

    assert li._assistant_groups is transcript._assistant_groups
