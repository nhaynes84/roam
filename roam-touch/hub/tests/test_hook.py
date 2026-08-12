"""The Claude Code hook that reports receipts and outcomes.

Mocked at the network boundary (`urllib.request.urlopen`) with a real temp
transcript on disk. The rule under test above all others: a hook must never be
able to disturb the session it reports on -- every failure path exits 0 and
posts nothing.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

HOOK_PATH = Path(__file__).resolve().parent.parent / "roam-hub-hook"


def load_hook():
    spec = importlib.util.spec_from_loader(
        "roam_hub_hook",
        importlib.machinery.SourceFileLoader("roam_hub_hook", str(HOOK_PATH)),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hook = load_hook()


@pytest.fixture
def posted(monkeypatch):
    """Capture what the hook would POST."""
    sent: list[dict] = []

    def fake_urlopen(request, timeout=None):
        sent.append(
            {
                "url": request.full_url,
                "headers": {k.lower(): v for k, v in request.headers.items()},
                "body": json.loads(request.data.decode()),
            }
        )

        class Response:
            def read(self):
                return b""

        return Response()

    monkeypatch.setattr(hook.urllib.request, "urlopen", fake_urlopen)
    return sent


@pytest.fixture
def hook_env(monkeypatch, tmp_path):
    token_file = tmp_path / "token.txt"
    token_file.write_text("hook-token\n", encoding="utf-8")
    monkeypatch.setenv("TMUX_PANE", "%4")
    monkeypatch.setenv("ROAM_HUB_TOKEN_FILE", str(token_file))
    monkeypatch.setenv("ROAM_HUB_URL", "http://hub.test:8787")
    return tmp_path


def run(monkeypatch, argv: list[str], stdin: str = "") -> int:
    monkeypatch.setattr(sys, "argv", ["roam-hub-hook", *argv])
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    return hook.main()


def transcript_with(tmp_path: Path, answer: str) -> str:
    path = tmp_path / "session.jsonl"
    path.write_text(
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "id": "m1",
                    "content": [{"type": "thinking", "thinking": "internal"}],
                },
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "assistant",
                "message": {"id": "m1", "content": [{"type": "text", "text": answer}]},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return str(path)


def test_outcome_carries_the_assistants_answer(monkeypatch, hook_env, posted):
    path = transcript_with(hook_env, "The build is green, 122 tests.")
    payload = json.dumps({"transcript_path": path, "session_id": "abc123"})
    assert run(monkeypatch, ["outcome"], payload) == 0
    body = posted[0]["body"]
    assert body["kind"] == "outcome"
    assert body["pane"] == "%4"
    assert body["body"] == "The build is green, 122 tests."
    assert body["meta"]["session_id"] == "abc123"
    assert body["meta"]["source"] == "claude-hook"
    assert posted[0]["headers"]["authorization"] == "Bearer hook-token"
    assert posted[0]["url"] == "http://hub.test:8787/events"


def test_the_payloads_own_answer_wins_over_the_transcript(monkeypatch, hook_env, posted):
    """Claude Code hands `Stop` the finished answer -- no disk race to lose.

    Captured from a real live turn on this box (claude-code 2.1.228): the Stop
    payload carries `last_assistant_message`. The transcript on disk may still
    be one flush behind, which is exactly how the wrong block got stored once.
    """
    path = transcript_with(hook_env, "stale preamble from the same turn")
    payload = json.dumps(
        {
            "hook_event_name": "Stop",
            "transcript_path": path,
            "session_id": "s1",
            "prompt_id": "p1",
            "last_assistant_message": "Installed and validated. Nothing else to do.",
        }
    )
    run(monkeypatch, ["outcome"], payload)
    body = posted[0]["body"]
    assert body["body"] == "Installed and validated. Nothing else to do."
    assert body["meta"]["answer_source"] == "hook_payload"
    assert body["meta"]["prompt_id"] == "p1"


def test_an_empty_payload_answer_falls_back_to_the_transcript(
    monkeypatch, hook_env, posted
):
    path = transcript_with(hook_env, "the answer from disk")
    payload = json.dumps({"transcript_path": path, "last_assistant_message": "   "})
    run(monkeypatch, ["outcome"], payload)
    assert posted[0]["body"]["body"] == "the answer from disk"
    assert posted[0]["body"]["meta"]["answer_source"] == "transcript"
    assert posted[0]["body"]["meta"]["transcript_settled"] is True


def test_the_transcript_fallback_waits_for_the_flush(monkeypatch, hook_env, posted):
    """The fallback must not repeat the original bug."""
    path = Path(hook_env) / "racy.jsonl"
    path.write_text(
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "id": "m1",
                    "content": [{"type": "text", "text": "Backing up first:"}],
                },
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "assistant",
                "message": {
                    "id": "m2",
                    "content": [{"type": "tool_use", "id": "t", "name": "Edit", "input": {}}],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    def flush(_seconds):
        with path.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "id": "m3",
                            "content": [
                                {"type": "text", "text": "Installed and validated."}
                            ],
                        },
                    }
                )
                + "\n"
            )

    import transcript as transcript_mod

    monkeypatch.setattr(transcript_mod.time, "sleep", flush)
    monkeypatch.setenv("ROAM_HUB_ANSWER_SOURCE", "transcript")
    run(monkeypatch, ["outcome"], json.dumps({"transcript_path": str(path)}))
    assert posted[0]["body"]["body"] == "Installed and validated."
    assert posted[0]["body"]["meta"]["transcript_settled"] is True


def test_an_unsettled_transcript_is_flagged_not_hidden(monkeypatch, hook_env, posted):
    path = Path(hook_env) / "stuck.jsonl"
    path.write_text(
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "id": "m1",
                    "content": [{"type": "text", "text": "Here is the plan:"}],
                },
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "assistant",
                "message": {
                    "id": "m2",
                    "content": [{"type": "tool_use", "id": "t", "name": "Edit", "input": {}}],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ROAM_HUB_ANSWER_SOURCE", "transcript")
    monkeypatch.setenv("ROAM_HUB_SETTLE_MS", "100")
    run(monkeypatch, ["outcome"], json.dumps({"transcript_path": str(path)}))
    meta = posted[0]["body"]["meta"]
    assert meta["answer_source"] == "transcript"
    assert meta["transcript_settled"] is False, "a wrong block must be detectable"


def test_settling_can_be_switched_off_for_diagnosis(monkeypatch, hook_env, posted):
    path = transcript_with(hook_env, "whatever is on disk")
    monkeypatch.setenv("ROAM_HUB_ANSWER_SOURCE", "transcript")
    monkeypatch.setenv("ROAM_HUB_SETTLE_MS", "0")
    run(monkeypatch, ["outcome"], json.dumps({"transcript_path": path}))
    assert posted[0]["body"]["body"] == "whatever is on disk"


def test_outcome_never_leaks_thinking(monkeypatch, hook_env, posted):
    path = transcript_with(hook_env, "Here is the answer.")
    run(monkeypatch, ["outcome"], json.dumps({"transcript_path": path}))
    assert "internal" not in posted[0]["body"]["body"]


def test_receipt_carries_the_submitted_prompt(monkeypatch, hook_env, posted):
    payload = json.dumps({"prompt": "run the deploy", "session_id": "s"})
    run(monkeypatch, ["receipt"], payload)
    assert posted[0]["body"]["kind"] == "receipt"
    assert posted[0]["body"]["body"] == "run the deploy"


def test_an_explicit_body_wins(monkeypatch, hook_env, posted):
    path = transcript_with(hook_env, "from the transcript")
    run(monkeypatch, ["outcome", "said by hand"], json.dumps({"transcript_path": path}))
    assert posted[0]["body"]["body"] == "said by hand"


def test_a_missing_transcript_still_posts_the_outcome(monkeypatch, hook_env, posted):
    run(monkeypatch, ["outcome"], json.dumps({"transcript_path": "/nope.jsonl"}))
    assert posted[0]["body"]["body"] == ""
    assert posted[0]["body"]["kind"] == "outcome"


def test_outside_tmux_nothing_is_posted(monkeypatch, hook_env, posted):
    monkeypatch.delenv("TMUX_PANE")
    assert run(monkeypatch, ["outcome"], "{}") == 0
    assert posted == []


def test_without_a_token_nothing_is_posted(monkeypatch, hook_env, posted):
    monkeypatch.setenv("ROAM_HUB_TOKEN_FILE", "/nonexistent/token.txt")
    assert run(monkeypatch, ["outcome"], "{}") == 0
    assert posted == []


def test_without_a_kind_nothing_is_posted(monkeypatch, hook_env, posted):
    assert run(monkeypatch, [], "{}") == 0
    assert posted == []


def test_junk_on_stdin_does_not_break_it(monkeypatch, hook_env, posted):
    assert run(monkeypatch, ["outcome"], "not json") == 0
    assert posted[0]["body"]["body"] == ""


def test_an_unreachable_hub_is_silent_and_exits_zero(monkeypatch, hook_env):
    def boom(request, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(hook.urllib.request, "urlopen", boom)
    assert run(monkeypatch, ["outcome"], "{}") == 0


def test_a_terminal_stdin_is_not_read(monkeypatch, hook_env, posted):
    class Tty(io.StringIO):
        def isatty(self):
            return True

        def read(self, *a):  # would block on a real terminal
            raise AssertionError("must not read from a tty")

    monkeypatch.setattr(sys, "argv", ["roam-hub-hook", "note", "manual"])
    monkeypatch.setattr(sys, "stdin", Tty())
    assert hook.main() == 0
    assert posted[0]["body"]["body"] == "manual"
