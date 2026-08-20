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
    DEFAULT_TAIL_BYTES,
    MAX_BODY_CHARS,
    MAX_SUMMARY_CHARS,
    cap_body,
    last_assistant_text,
    settled_assistant_text,
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


# ------------------------------------------------------------- the flush race
#
# Live incident, 2026-08-11: the Stop hook read the transcript 143 ms *after*
# the final assistant record's own timestamp and still did not see it, so the
# extractor walked back and stored the turn's opening line -- real, plausible
# prose from the same turn, wrong block, no way to tell.


def append_records(path: Path, records: list[dict]) -> None:
    with path.open("a", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record) + "\n")


def flushing_sleeper(path: Path, schedule: dict[int, list[dict]]):
    """A fake `sleep` that flushes more of the turn on the given polls."""
    state = {"n": 0}

    def sleeper(_seconds: float) -> None:
        state["n"] += 1
        if state["n"] in schedule:
            append_records(path, schedule[state["n"]])

    return sleeper


def test_the_answer_that_lands_on_the_second_read_is_the_one_returned(tmp_path):
    path = write_jsonl(
        tmp_path / "t.jsonl",
        [
            assistant("m1", text("Backing up first, then merging rather than replacing:")),
            assistant("m2", tool_use("Edit")),
        ],
    )
    body, settled = settled_assistant_text(
        path,
        timeout=2.0,
        sleep=flushing_sleeper(
            path, {2: [assistant("m3", text("Installed and validated."))]}
        ),
    )
    assert body == "Installed and validated.", "the preamble is not the answer"
    assert settled is True


def test_an_answer_that_takes_three_reads_is_still_caught(tmp_path):
    path = write_jsonl(
        tmp_path / "t.jsonl",
        [assistant("m1", text("Working on it:")), assistant("m2", tool_use())],
    )
    body, settled = settled_assistant_text(
        path,
        timeout=2.0,
        sleep=flushing_sleeper(
            path,
            {
                1: [assistant("m3", thinking("nearly there"))],
                3: [assistant("m4", text("Done — the suite is green."))],
            },
        ),
    )
    assert body == "Done — the suite is green."
    assert settled is True


def test_an_already_complete_turn_returns_without_waiting(tmp_path):
    """The common case must cost nothing: no sleep at all."""
    path = write_jsonl(tmp_path / "t.jsonl", [assistant("m1", text("The answer."))])

    def must_not_sleep(_seconds: float) -> None:
        raise AssertionError("a settled transcript must not be polled")

    body, settled = settled_assistant_text(path, sleep=must_not_sleep)
    assert (body, settled) == ("The answer.", True)


def test_the_cap_expires_and_says_so(tmp_path):
    """The answer never arrives: post the best we have, flagged unsettled."""
    path = write_jsonl(
        tmp_path / "t.jsonl",
        [
            assistant("m1", text("Here is the plan:")),
            assistant("m2", tool_use("Edit")),
        ],
    )
    ticks = {"t": 0.0}

    def clock() -> float:
        return ticks["t"]

    def sleeper(seconds: float) -> None:
        ticks["t"] += seconds
        append_records(path, [assistant("m2", tool_use("Edit"))])  # busy, silent

    body, settled = settled_assistant_text(
        path, timeout=2.0, quiet_after=0, sleep=sleeper, clock=clock
    )
    assert body == "Here is the plan:"
    assert settled is False, "an unsettled body must be detectable, not silent"
    assert ticks["t"] <= 2.1, "the wait is hard-capped"


def test_a_file_that_never_changes_gives_up_early(tmp_path):
    """A quiet file means nothing is coming -- don't burn the whole window."""
    path = write_jsonl(
        tmp_path / "t.jsonl",
        [assistant("m1", text("An older answer.")), assistant("m2", tool_use())],
    )
    ticks = {"t": 0.0}

    def clock() -> float:
        return ticks["t"]

    def sleeper(seconds: float) -> None:
        ticks["t"] += seconds

    body, settled = settled_assistant_text(
        path, timeout=10.0, quiet_after=0.4, sleep=sleeper, clock=clock
    )
    assert body == "An older answer."
    assert settled is False
    assert ticks["t"] < 1.0, "gave up long before the hard cap"


def test_a_turn_that_ends_in_tools_after_the_settle_is_flagged(tmp_path):
    """Interrupted turn: tool calls keep landing, an answer never does."""
    path = write_jsonl(
        tmp_path / "t.jsonl",
        [assistant("m1", text("Starting.")), assistant("m2", tool_use("Bash"))],
    )
    ticks = {"t": 0.0}
    calls = {"n": 0}

    def sleeper(seconds: float) -> None:
        ticks["t"] += seconds
        calls["n"] += 1
        append_records(path, [assistant(f"m{calls['n'] + 2}", tool_use("Bash"))])

    body, settled = settled_assistant_text(
        path,
        timeout=0.3,
        quiet_after=0,
        sleep=sleeper,
        clock=lambda: ticks["t"],
    )
    assert body == "Starting.", "the only text there is, and it is flagged"
    assert settled is False
    from transcript import _assistant_groups, _ends_with_text

    assert not _ends_with_text(_assistant_groups(path, DEFAULT_TAIL_BYTES))


def test_settling_a_missing_file_is_empty_and_unsettled(tmp_path):
    body, settled = settled_assistant_text(
        tmp_path / "nope.jsonl", timeout=0.1, quiet_after=0, sleep=lambda s: None
    )
    assert body == ""
    assert settled is False


def test_ends_with_text_distinguishes_a_finished_turn(tmp_path):
    finished = write_jsonl(
        tmp_path / "a.jsonl",
        [assistant("m1", tool_use()), assistant("m2", text("done"))],
    )
    mid_turn = write_jsonl(
        tmp_path / "b.jsonl",
        [assistant("m1", text("about to")), assistant("m2", tool_use())],
    )
    from transcript import _assistant_groups, _ends_with_text

    assert _ends_with_text(_assistant_groups(finished, DEFAULT_TAIL_BYTES)) is True
    assert _ends_with_text(_assistant_groups(mid_turn, DEFAULT_TAIL_BYTES)) is False


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


def _has_any_assistant_text(path) -> bool:
    """A session killed before its first text turn has nothing to extract --
    every assistant record is tool_use/thinking only. Those are not parser
    failures; skip them rather than asserting text into existence."""
    import json
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get("type") != "assistant":
                continue
            content = (record.get("message") or {}).get("content") or []
            for block in content:
                if (
                    isinstance(block, dict)
                    and block.get("type") == "text"
                    and (block.get("text") or "").strip()
                ):
                    return True
    return False


@pytest.mark.skipif(not REAL_TRANSCRIPTS, reason="no local transcripts")
@pytest.mark.parametrize("path", REAL_TRANSCRIPTS)
def test_every_real_transcript_on_this_box_yields_clean_text(path):
    """Fidelity: run against the actual JSONL Claude Code writes here."""
    if not _has_any_assistant_text(path):
        pytest.skip("session produced no assistant text at all (interrupted turns only)")
    answer = last_assistant_text(path)
    assert answer, f"no assistant text found in {path}"
    assert '"type"' not in answer, "raw JSON leaked into the answer"
    assert "tool_use" not in answer
    short = summarise(answer)
    assert short and len(short) <= MAX_SUMMARY_CHARS + 1
    assert "```" not in short
