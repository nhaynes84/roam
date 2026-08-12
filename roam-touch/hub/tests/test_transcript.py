"""Pulling the answer out of a session transcript, and making it readable.

The shapes here are the ones that actually occur in
`~/.claude/projects/-Users-talos/*.jsonl`: one turn spread over several records
sharing a `message.id`, thinking blocks that must never be spoken, and turns
that are nothing but tool calls.
"""

from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import pytest

from transcript import (
    MAX_BODY_CHARS,
    MAX_SUMMARY_CHARS,
    cap_body,
    last_assistant_text,
    summarise,
)

REAL_TRANSCRIPTS = sorted(
    glob.glob(os.path.expanduser("~/.claude/projects/-Users-talos/*.jsonl"))
)


def write_jsonl(path: Path, records: list[dict]) -> Path:
    path.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )
    return path


def assistant(message_id: str, *blocks: dict, sidechain: bool = False) -> dict:
    return {
        "type": "assistant",
        "isSidechain": sidechain,
        "message": {"id": message_id, "role": "assistant", "content": list(blocks)},
    }


def text(value: str) -> dict:
    return {"type": "text", "text": value}


def thinking(value: str) -> dict:
    return {"type": "thinking", "thinking": value}


def tool_use(name: str = "Bash") -> dict:
    return {"type": "tool_use", "id": "toolu_1", "name": name, "input": {}}


# ------------------------------------------------------------- extraction


def test_last_answer_is_returned(tmp_path):
    path = write_jsonl(
        tmp_path / "t.jsonl",
        [
            {"type": "user", "message": {"role": "user", "content": "hi"}},
            assistant("m1", text("first answer")),
            assistant("m2", text("the last answer")),
        ],
    )
    assert last_assistant_text(path) == "the last answer"


def test_a_turn_split_across_records_is_joined(tmp_path):
    """The real shape: one message id, several records, thinking first."""
    path = write_jsonl(
        tmp_path / "t.jsonl",
        [
            assistant("m9", thinking("weighing it up")),
            assistant("m9", text("Part one.")),
            assistant("m9", text("Part two.")),
        ],
    )
    assert last_assistant_text(path) == "Part one.\n\nPart two."


def test_multiple_text_blocks_in_one_record_are_joined(tmp_path):
    path = write_jsonl(
        tmp_path / "t.jsonl",
        [assistant("m1", text("Alpha."), text("Beta."))],
    )
    assert last_assistant_text(path) == "Alpha.\n\nBeta."


def test_thinking_is_never_included(tmp_path):
    path = write_jsonl(
        tmp_path / "t.jsonl",
        [assistant("m1", thinking("the user is wrong about X"), text("Sure."))],
    )
    result = last_assistant_text(path)
    assert result == "Sure."
    assert "wrong about X" not in result


def test_a_tool_only_final_turn_walks_back_to_the_last_real_answer(tmp_path):
    path = write_jsonl(
        tmp_path / "t.jsonl",
        [
            assistant("m1", text("Here is what I found.")),
            assistant("m2", thinking("now run it")),
            assistant("m2", tool_use()),
            assistant("m3", tool_use("Read")),
        ],
    )
    assert last_assistant_text(path) == "Here is what I found."


def test_a_thinking_only_final_turn_walks_back(tmp_path):
    path = write_jsonl(
        tmp_path / "t.jsonl",
        [assistant("m1", text("The answer.")), assistant("m2", thinking("hmm"))],
    )
    assert last_assistant_text(path) == "The answer."


def test_subagent_output_is_not_the_sessions_answer(tmp_path):
    path = write_jsonl(
        tmp_path / "t.jsonl",
        [
            assistant("m1", text("main agent answer")),
            assistant("m2", text("subagent chatter"), sidechain=True),
        ],
    )
    assert last_assistant_text(path) == "main agent answer"


def test_string_content_is_accepted(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text(
        json.dumps(
            {"type": "assistant", "message": {"id": "m1", "content": "plain string"}}
        )
        + "\n",
        encoding="utf-8",
    )
    assert last_assistant_text(path) == "plain string"


def test_nothing_but_tools_yields_empty(tmp_path):
    path = write_jsonl(tmp_path / "t.jsonl", [assistant("m1", tool_use())])
    assert last_assistant_text(path) == ""


def test_missing_file_is_empty_not_an_error():
    assert last_assistant_text("/nonexistent/path/session.jsonl") == ""


def test_empty_file_is_empty(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    assert last_assistant_text(path) == ""


def test_a_directory_instead_of_a_file_is_empty(tmp_path):
    assert last_assistant_text(tmp_path) == ""


def test_unparseable_and_half_written_lines_are_skipped(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text(
        json.dumps(assistant("m1", text("good answer")))
        + "\nnot json at all\n"
        + '{"type": "assistant", "message": {"id": "m2", "cont',
        encoding="utf-8",
    )
    assert last_assistant_text(path) == "good answer"


def test_tail_reading_discards_a_partial_first_record(tmp_path):
    """Sessions reach tens of MB; only the tail is read."""
    path = write_jsonl(
        tmp_path / "t.jsonl",
        [assistant("m1", text("x" * 5000)), assistant("m2", text("the tail answer"))],
    )
    assert last_assistant_text(path, tail_bytes=200) == "the tail answer"


def test_non_assistant_records_are_ignored(tmp_path):
    path = write_jsonl(
        tmp_path / "t.jsonl",
        [
            assistant("m1", text("the answer")),
            {"type": "user", "message": {"role": "user", "content": "thanks"}},
            {"type": "system", "content": "hook ran"},
            {"type": "ai-title", "title": "a session"},
        ],
    )
    assert last_assistant_text(path) == "the answer"


# ------------------------------------------------------- speech and glance


def test_summary_strips_markdown_scaffolding():
    body = "## Heading\n\n- **bold** point with `inline code`\n- [a link](http://x)\n"
    out = summarise(body)
    assert out == "Heading bold point with inline code a link"


def test_summary_notes_code_blocks_instead_of_reading_them_out():
    body = "Run this:\n\n```bash\nls -la\ncd /tmp\n```\n\nThen you are done."
    out = summarise(body)
    assert "[code, 2 lines]" in out
    assert "ls -la" not in out
    assert out.startswith("Run this:")
    assert out.endswith("Then you are done.")


def test_summary_notes_tables_instead_of_reading_them_out():
    body = "Results:\n\n| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n\nThat is all."
    out = summarise(body)
    assert "[table, 2 rows]" in out
    assert "|" not in out


def test_summary_drops_decorative_symbols_piper_cannot_speak():
    assert summarise("★ Done ⚠️ mostly ✳") == "Done mostly"


def test_summary_collapses_whitespace():
    assert summarise("one\n\n\ntwo   three\n") == "one two three"


def test_summary_cuts_at_a_sentence_boundary():
    body = "First sentence is here. " + "Second sentence padding. " * 40
    out = summarise(body, limit=60)
    assert out.endswith(".")
    assert len(out) <= 60
    assert "…" not in out


def test_summary_falls_back_to_a_word_boundary_with_an_ellipsis():
    out = summarise("word " * 100, limit=40)
    assert out.endswith("…")
    assert len(out) <= 41


def test_short_plain_text_is_its_own_summary():
    assert summarise("Deploy finished, all green.") == "Deploy finished, all green."


def test_summary_of_nothing_is_nothing():
    assert summarise("") == ""


def test_default_summary_limit_is_glanceable():
    out = summarise("x" * 5000)
    assert len(out) <= MAX_SUMMARY_CHARS + 1


# ------------------------------------------------------------------- caps


def test_cap_leaves_normal_bodies_alone():
    assert cap_body("a normal answer") == ("a normal answer", None)


def test_cap_truncates_and_reports_the_original_length():
    body, original = cap_body("y" * (MAX_BODY_CHARS + 500))
    assert original == MAX_BODY_CHARS + 500
    assert len(body) == MAX_BODY_CHARS
    assert body.endswith("… [truncated]")


def test_cap_handles_empty():
    assert cap_body("") == ("", None)


# ------------------------------------------- the real files on this machine


@pytest.mark.skipif(not REAL_TRANSCRIPTS, reason="no local transcripts")
@pytest.mark.parametrize("path", REAL_TRANSCRIPTS)
def test_every_real_transcript_on_this_box_yields_clean_text(path):
    """Fidelity: run against the actual JSONL Claude Code writes here."""
    answer = last_assistant_text(path)
    assert answer, f"no assistant text found in {path}"
    assert '"type"' not in answer, "raw JSON leaked into the answer"
    assert "tool_use" not in answer
    short = summarise(answer)
    assert short and len(short) <= MAX_SUMMARY_CHARS + 1
    assert "```" not in short
