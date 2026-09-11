"""Channel layer. The device's entire job is "send this to exactly that", so
the flags used to talk to tmux are the contract under test."""

from __future__ import annotations

import pytest

import channels as channels_mod
from channels import Channel, TmuxError


def test_list_channels_parses_the_tab_separated_format(fake_tmux):
    found = channels_mod.list_channels()
    assert [c.pane_id for c in found] == ["%0", "%1"]
    first = found[0]
    assert first.session == "main"
    assert first.window == 0 and first.index == 0
    assert first.command == "node"
    assert first.title == "◑ Roam Touch rebuild discussion"


def test_pane_title_with_spaces_and_punctuation_survives(fake_tmux):
    fake_tmux.retitle("%0", "fix: the 3.9\" panel, again -- part 2")
    assert channels_mod.list_channels()[0].title == 'fix: the 3.9" panel, again -- part 2'


def test_label_prefers_the_pane_title(fake_tmux):
    """The Claude session summary in the pane title IS the channel name."""
    assert channels_mod.list_channels()[0].label == "◑ Roam Touch rebuild discussion"


def test_label_falls_back_to_session_window_pane(fake_tmux):
    fake_tmux.retitle("%1", "")
    labels = {c.pane_id: c.label for c in channels_mod.list_channels()}
    assert labels["%1"] == "augment:1.0"


def test_label_ignores_a_title_that_is_just_the_session_name(fake_tmux):
    fake_tmux.retitle("%1", "augment")
    labels = {c.pane_id: c.label for c in channels_mod.list_channels()}
    assert labels["%1"] == "augment:1.0"


def test_label_ignores_tmuxs_default_hostname_title(fake_tmux):
    """A bare shell pane reports the hostname as its title. Verified live on
    talos: every unnamed pane would otherwise be called "talos"."""
    fake_tmux.retitle("%1", channels_mod._DEFAULT_TITLE.upper())
    labels = {c.pane_id: c.label for c in channels_mod.list_channels()}
    assert labels["%1"] == "augment:1.0"


def test_no_tmux_server_is_an_empty_list_not_an_error(fake_tmux):
    fake_tmux.server_running = False
    assert channels_mod.list_channels() == []


def test_tmux_missing_raises(fake_tmux):
    fake_tmux.installed = False
    with pytest.raises(TmuxError):
        channels_mod.list_channels()


def test_get_and_exists(fake_tmux):
    assert channels_mod.get("%1").session == "augment"
    assert channels_mod.get("%9") is None
    assert channels_mod.exists("%0") is True
    assert channels_mod.exists("%9") is False


# ----------------------------------------------------------------- sending


def _pasted(fake_tmux) -> list[str]:
    """The stdin of every load-buffer call -- i.e. what was pasted."""
    return [s for a, s in fake_tmux.calls if a and a[0] == "load-buffer"]


def test_send_goes_as_a_bracketed_paste_and_a_separate_enter(fake_tmux):
    """★ ALWAYS a bracketed paste now, never a `send-keys -l` burst -- a literal
    keystroke burst dropped characters when the TUI was under render pressure."""
    fake_tmux.pane_output["%0"] = "deploy the thing"  # so the input-landed poll returns fast
    channels_mod.send("%0", "deploy the thing")
    assert _pasted(fake_tmux) == ["deploy the thing"]
    assert "-p" in fake_tmux.argv_for("paste-buffer")[0]  # bracketed
    # Enter is always a separate, deliberate keystroke.
    assert fake_tmux.argv_for("send-keys") == [("send-keys", "-t", "%0", "Enter")]


def test_send_does_not_execute_key_names_in_the_transcript(fake_tmux):
    """A transcript with "Enter"/"C-c" must be TYPED, never interpreted. Paste
    carries it verbatim; the only send-keys call is the final Enter."""
    text = "press Enter then C-c to stop it"
    fake_tmux.pane_output["%0"] = text
    channels_mod.send("%0", text)
    assert _pasted(fake_tmux) == [text]
    assert fake_tmux.argv_for("send-keys") == [("send-keys", "-t", "%0", "Enter")]


def test_send_survives_a_leading_dash(fake_tmux):
    """Regression: a leading dash was read as a tmux option and the message
    dropped. Paste via load-buffer stdin is immune to option parsing."""
    text = "-N is not a flag here"
    fake_tmux.pane_output["%0"] = text
    channels_mod.send("%0", text)
    assert _pasted(fake_tmux) == [text]


def test_send_without_enter_stages_the_text(fake_tmux):
    """enter=False pastes the text but does NOT submit it -- no Enter keystroke."""
    channels_mod.send("%0", "half a thought", enter=False)
    assert _pasted(fake_tmux) == ["half a thought"]
    assert fake_tmux.argv_for("send-keys") == []


def test_multiline_text_goes_as_one_bracketed_paste(fake_tmux):
    """Typing a literal newline into a TUI submits the line -- three lines
    would fire as three prompts. Bracketed paste keeps it one message."""
    channels_mod.send("%0", "line one\nline two\nline three")
    loads = [(a, s) for a, s in fake_tmux.calls if a[0] == "load-buffer"]
    assert loads[0][1] == "line one\nline two\nline three"
    paste = fake_tmux.argv_for("paste-buffer")[0]
    assert "-p" in paste and "-d" in paste
    assert paste[paste.index("-t") + 1] == "%0"
    # ...and the submit is still a deliberate, separate keystroke.
    assert fake_tmux.argv_for("send-keys") == [("send-keys", "-t", "%0", "Enter")]


def test_send_to_a_dead_pane_raises_before_typing_anything(fake_tmux):
    fake_tmux.kill_pane("%1")
    with pytest.raises(TmuxError, match="no such pane"):
        channels_mod.send("%1", "into the void")
    assert fake_tmux.argv_for("send-keys") == []


def test_send_refuses_empty_text(fake_tmux):
    with pytest.raises(ValueError):
        channels_mod.send("%0", "")
    assert fake_tmux.argv_for("send-keys") == []


def test_send_propagates_a_tmux_failure(fake_tmux):
    fake_tmux.fail_send_with = "pane is dead"
    with pytest.raises(TmuxError, match="pane is dead"):
        channels_mod.send("%0", "hello")


# ---------------------------------------------------------------- capturing


def test_capture_asks_for_the_requested_scrollback(fake_tmux):
    fake_tmux.pane_output["%0"] = "the last thing Claude said\n"
    assert channels_mod.capture("%0", lines=50) == "the last thing Claude said\n"
    argv = fake_tmux.argv_for("capture-pane")[0]
    assert argv == ("capture-pane", "-p", "-J", "-t", "%0", "-S", "-50")


def test_capture_of_a_dead_pane_raises(fake_tmux):
    with pytest.raises(TmuxError, match="no such pane"):
        channels_mod.capture("%9")


def test_screen_digest_changes_only_when_the_screen_changes(fake_tmux):
    """The liveness signal: tmux 3.7b has no per-pane activity timestamp."""
    fake_tmux.pane_output["%0"] = "thinking… 12s"
    first = channels_mod.screen_digest("%0")
    assert first == channels_mod.screen_digest("%0")
    fake_tmux.pane_output["%0"] = "thinking… 13s"
    assert channels_mod.screen_digest("%0") != first


def test_screen_digest_reads_the_visible_screen_only(fake_tmux):
    channels_mod.screen_digest("%0")
    argv = fake_tmux.argv_for("capture-pane")[0]
    assert argv == ("capture-pane", "-p", "-t", "%0")
    assert "-S" not in argv, "scrollback would make this expensive"


def test_screen_digest_of_a_dead_pane_is_empty_not_an_error(fake_tmux):
    fake_tmux.kill_pane("%0")
    fake_tmux.installed = False
    assert channels_mod.screen_digest("%0") == ""


def test_channel_to_dict_carries_the_label(fake_tmux):
    payload = channels_mod.list_channels()[0].to_dict()
    assert payload["pane_id"] == "%0"
    assert payload["label"] == "◑ Roam Touch rebuild discussion"


# --------------------------------------------------------------- busy detection

#: A pane genuinely mid-reply. Captured off %42 on 2026-09-07: the interrupt hint
#: lives in the FOOTER, second line from the bottom, alongside the permissions hint.
BUSY_SCREEN = """\
  Some earlier reply text that has nothing to do with the footer.

✻ Transmuting… (1m 43s · ↓ 6.0k tokens)

────────────────────────────────────────────
❯
────────────────────────────────────────────
  ⏵⏵ bypass permissions on (shift+tab to cycle) · esc to interrupt · ← for agents
  ⧉  gaggiuino-build-sheet
"""

#: ⚠️⚠️ THE REGRESSION. Captured off %24 on 2026-09-07: an agent EXPLAINING the busy
#: mechanism put the marker in its own transcript, on line 5 of 59. The footer has
#: none -- the pane is idle at its prompt -- but a whole-screen substring match
#: pinned it `working` for 17 minutes and silently swallowed a queued message.
IDLE_SCREEN_DISCUSSING_THE_MARKER = """\
  Both parts scoped now. Here's the reality of adding it as a model option:

  - Busy/status — my busy-detection keys on Claude's "esc to interrupt" footer;
  codex's TUI differs, so status/queue-on-busy would misread a codex pane.

✻ Churned for 22s

────────────────────────────────────────────
❯
────────────────────────────────────────────
  ⏵⏵ bypass permissions on (shift+tab to cycle) · ← for agents
  ⧉  yellow-gaggia
"""


class TestBusyReadsTheFooterOnly:
    """The hint is TUI chrome. Matching it anywhere on screen means any pane that
    writes about it pins itself busy, and a held message then never flushes."""

    def test_a_pane_mid_reply_is_busy(self, fake_tmux):
        fake_tmux.pane_output["%0"] = BUSY_SCREEN
        assert channels_mod.busy("%0") is True

    def test_a_pane_merely_discussing_the_marker_is_not_busy(self, fake_tmux):
        fake_tmux.pane_output["%0"] = IDLE_SCREEN_DISCUSSING_THE_MARKER
        assert channels_mod.busy("%0") is False

    def test_an_ordinary_idle_pane_is_not_busy(self, fake_tmux):
        fake_tmux.pane_output["%0"] = "❯\n  ⏵⏵ bypass permissions on · ← for agents\n"
        assert channels_mod.busy("%0") is False

    def test_the_marker_just_above_the_window_does_not_count(self, fake_tmux):
        """Guards the window size itself: one line further up is transcript."""
        body = "\n".join(["esc to interrupt"] + ["filler"] * channels_mod.BUSY_TAIL_LINES)
        fake_tmux.pane_output["%0"] = body + "\n"
        assert channels_mod.busy("%0") is False

    def test_a_dead_pane_is_not_busy(self, fake_tmux):
        fake_tmux.pane_output["%0"] = ""
        assert channels_mod.busy("%0") is False
