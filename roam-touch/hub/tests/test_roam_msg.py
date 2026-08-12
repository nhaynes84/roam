"""`tools/roam-msg` -- the thin client every agent on this box calls.

⚠️ The rule this file exists to hold: **`roam-msg` never touches the phone.**

It used to. It shelled out to `adb ... cmd notification post`, which meant the
hub's notification policy governed outcomes and nothing else, and the device
rang all day while he sat at the keyboard. A later patch made the script ask
`GET /presence` and decide for itself -- a second copy of the policy, in bash,
free to drift from the hub's. Both are gone: the script states what happened,
the hub decides, the bridge delivers.

So the tests here are mostly about what the script *cannot* do.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import io
import json
import urllib.error
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[3] / "tools"
ROAM_MSG = TOOLS / "roam-msg"
ROAM_PUSH = TOOLS / "roam-push"


def python_code(path: Path) -> str:
    """Source with comments and string literals stripped out.

    The guards below assert what a program *cannot do*, and every one of these
    files explains the rule it obeys in its own docstring. Grepping raw text
    would fail on the explanation and pass on the violation.
    """
    import tokenize

    with path.open(encoding="utf-8") as fh:
        return " ".join(
            token.string
            for token in tokenize.generate_tokens(fh.readline)
            if token.type not in (tokenize.COMMENT, tokenize.STRING)
            and not tokenize.tok_name[token.type].startswith("FSTRING")
        )


def shell_code(path: Path) -> str:
    return "\n".join(
        line for line in path.read_text().splitlines() if not line.lstrip().startswith("#")
    )


def load(path: Path, name: str):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, str(path))
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


msg = load(ROAM_MSG, "roam_msg")


@pytest.fixture
def hub(monkeypatch):
    """Capture what `roam-msg` POSTs, and answer as the hub would."""

    class FakeHub:
        def __init__(self) -> None:
            self.posts: list[tuple[str, dict]] = []
            self.reply: dict = {
                "event": {"id": 7, "pane_id": "%3", "kind": "notice"},
                "push": True,
                "reason": "nothing recorded -- unknown means push",
            }
            self.error: Exception | None = None

        def __call__(self, request, timeout=None):
            self.posts.append((request.full_url, json.loads(request.data)))
            if self.error:
                raise self.error
            return io.BytesIO(json.dumps(self.reply).encode())

    fake = FakeHub()
    monkeypatch.setattr(msg.urllib.request, "urlopen", fake)
    monkeypatch.setattr(msg, "read_token", lambda _settings: "test-token")
    return fake


def run(argv, env=None, hub_env=None):
    """`main` with a controlled environment; returns (code, out, err)."""
    out, err = io.StringIO(), io.StringIO()
    environ = {"ROAM_HUB": "http://hub.test:8787"}
    environ.update(env or {})
    code = msg.main(list(argv), env=environ, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


# ------------------------------------------------- it goes through the hub


def test_the_message_is_posted_to_the_hub(hub):
    code, out, _ = run(["build finished"])
    assert code == 0
    url, payload = hub.posts[0]
    assert url == "http://hub.test:8787/notify"
    assert payload["text"] == "build finished"
    assert payload["source"] == "roam-msg"


def test_the_words_are_joined_exactly_as_the_old_script_did(hub):
    run(["two", "words"])
    assert hub.posts[0][1]["text"] == "two words"


def test_nothing_to_send_is_an_error_and_posts_nothing(hub):
    code, _, err = run([])
    assert code == 1
    assert "nothing to send" in err
    assert hub.posts == []


# ------------------------------------------------------------ attribution


def test_a_message_from_a_tmux_pane_claims_that_channel(hub):
    """This is what makes suppression work at all: the hub can only apply
    'he is typing in that pane' if the message says which pane it came from."""
    run(["hi"], env={"TMUX_PANE": "%3"})
    assert hub.posts[0][1]["pane"] == "%3"


def test_an_explicit_pane_wins_over_the_environment(hub):
    run(["--pane", "1", "hi"], env={"TMUX_PANE": "%3"})
    assert hub.posts[0][1]["pane"] == "%1"


def test_with_no_pane_at_all_the_message_claims_nothing(hub):
    """An agent under launchd has no pane. It must not borrow one -- the hub
    files it on the host channel and pushes, because nothing covers it."""
    run(["hi"])
    assert "pane" not in hub.posts[0][1]


def test_the_pane_flag_survives_from_the_old_signature(hub):
    """`roam-msg --pane N "text"` is what the bridge and the docs say. Keep it."""
    code, _, _ = run(["--pane", "0", "still", "here"])
    assert code == 0
    assert hub.posts[0][1] == {
        "text": "still here",
        "pane": "%0",
        "source": "roam-msg",
        "meta": {"host": msg.HOSTNAME},
    }


# ------------------------------------------------------- saying what happened


def test_it_says_when_the_hub_will_push(hub):
    _, out, _ = run(["hi"])
    assert "%3" in out  # the channel it landed on, from the hub's own answer
    assert "push" in out.lower()


def test_it_says_when_the_hub_suppressed_the_push(hub):
    hub.reply = {
        "event": {"id": 8, "pane_id": "%0", "kind": "notice"},
        "push": False,
        "reason": "covered by tmux-input",
    }
    code, out, _ = run(["hi"])
    assert code == 0  # recorded is not failed
    assert "covered by tmux-input" in out
    assert "no push" in out.lower()


# ------------------------------------------------------------- the fallback


def test_an_unreachable_hub_drops_the_message_loudly(hub, monkeypatch, tmp_path):
    """★ The fallback decision: **drop, never go direct.**

    A direct path would only ever fire while the hub is down -- which is
    exactly when the bridge is down too, so every real outcome is stalling
    silently. Agent chatter arriving on the phone at that moment says the
    pipeline is healthy when it is not. So the message is dropped, spooled for
    the record, and the failure is stated on stderr.
    """
    monkeypatch.setattr(msg, "SPOOL", tmp_path / "undelivered.log")
    hub.error = urllib.error.URLError("connection refused")
    code, out, err = run(["the hub is down"])
    assert code == 1
    assert "not delivered" in err.lower()
    assert "the hub is down" in (tmp_path / "undelivered.log").read_text()


def test_a_hub_that_answers_with_an_error_is_also_a_drop(hub, monkeypatch, tmp_path):
    monkeypatch.setattr(msg, "SPOOL", tmp_path / "undelivered.log")
    hub.error = urllib.error.HTTPError(
        "http://hub.test:8787/notify", 401, "Unauthorized", {}, None
    )
    code, _, err = run(["hi"])
    assert code == 1
    assert "401" in err


def test_a_missing_token_drops_rather_than_finding_another_way(monkeypatch, tmp_path):
    monkeypatch.setattr(msg, "SPOOL", tmp_path / "undelivered.log")
    monkeypatch.setattr(
        msg, "read_token", lambda _s: (_ for _ in ()).throw(OSError("no token"))
    )
    code, _, err = run(["hi"])
    assert code == 1
    assert "token" in err.lower()


# ------------------------------------ ⚠️ no second route, no second policy


def test_roam_msg_cannot_reach_the_device_at_all():
    """The whole architectural point, asserted against the source: there is no
    `adb` in the client any more. If this fails, the phone has a second path
    into it and the hub is no longer the arbiter of anything."""
    source = python_code(ROAM_MSG)
    assert "adb" not in source
    assert "notification" not in source


def test_roam_msg_does_not_second_guess_the_hub():
    """It must not read `/presence` and decide for itself: that is the hub's
    policy, and a copy of it in a client is a copy that drifts."""
    assert "presence" not in python_code(ROAM_MSG)


def test_the_device_transport_is_a_separate_command_that_never_calls_the_hub():
    """`roam-push` is the bridge's arm and the only thing that speaks adb. It
    must not post notices back to the hub, or a pushed notice would become a
    new notice and the two would feed each other forever."""
    assert ROAM_PUSH.exists(), "the device transport must live on its own"
    source = shell_code(ROAM_PUSH)
    assert "adb" in source
    assert "notify" not in source
    assert "curl" not in source


def test_the_bridge_pushes_through_the_device_transport_not_the_client():
    """If the bridge ever shells out to `roam-msg` again, every notification it
    delivers posts a fresh notice to the hub, which the bridge then delivers."""
    import bridge as bridge_mod

    assert bridge_mod.Settings().roam_push.name == "roam-push"
    assert "roam_msg" not in python_code(Path(bridge_mod.__file__))
