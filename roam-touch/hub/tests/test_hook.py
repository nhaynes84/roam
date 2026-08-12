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
