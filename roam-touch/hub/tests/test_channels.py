"""Channel layer. The device's entire job is "send this to exactly that", so
the flags used to talk to tmux are the contract under test."""

from __future__ import annotations

import time

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


def test_send_uses_literal_keys_and_a_separate_enter(fake_tmux):
    channels_mod.send("%0", "deploy the thing")
    sends = fake_tmux.argv_for("send-keys")
    assert sends[0] == ("send-keys", "-t", "%0", "-l", "--", "deploy the thing")
    assert sends[1] == ("send-keys", "-t", "%0", "Enter")


def test_send_does_not_execute_key_names_in_the_transcript(fake_tmux):
    """Without -l, "Enter" and "C-c" in a transcript become keystrokes."""
    channels_mod.send("%0", "press Enter then C-c to stop it")
    first = fake_tmux.argv_for("send-keys")[0]
    assert "-l" in first
    assert first[-1] == "press Enter then C-c to stop it"


def test_send_survives_a_leading_dash(fake_tmux):
    """Regression: tmux read `-N ...` as an option and dropped the message."""
    channels_mod.send("%0", "-N is not a flag here")
    first = fake_tmux.argv_for("send-keys")[0]
    assert first[-2] == "--"
    assert first[-1] == "-N is not a flag here"


def test_send_without_enter_stages_the_text(fake_tmux):
    channels_mod.send("%0", "half a thought", enter=False)
    assert len(fake_tmux.argv_for("send-keys")) == 1


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


# ------------------------------------------------- who is watching what


def test_the_front_pane_of_a_recently_used_client_is_watched(fake_tmux):
    """"He is sitting in this pane" = the front pane of a client he just typed into."""
    fake_tmux.clients = {"main": time.time() - 5}
    assert channels_mod.watched_panes(grace_s=120) == {"%0"}


def test_a_client_he_walked_away_from_is_not_watched(fake_tmux):
    """68 minutes without a keystroke means the screen is not telling him anything."""
    fake_tmux.clients = {"main": time.time() - 5, "augment": time.time() - 4000}
    assert channels_mod.watched_panes(grace_s=120) == {"%0"}


def test_several_attached_clients_are_all_watched(fake_tmux):
    fake_tmux.clients = {"main": time.time() - 1, "augment": time.time() - 2}
    assert channels_mod.watched_panes(grace_s=120) == {"%0", "%1"}


def test_no_attached_client_means_nothing_is_watched(fake_tmux):
    fake_tmux.clients = {}
    assert channels_mod.watched_panes() == set()


def test_grace_zero_ignores_recency(fake_tmux):
    fake_tmux.clients = {"augment": time.time() - 99999}
    assert channels_mod.watched_panes(grace_s=0) == {"%1"}


def test_a_client_with_an_unparseable_activity_is_treated_as_stale(fake_tmux):
    fake_tmux.clients = {"main": "not-a-number"}
    assert channels_mod.watched_panes(grace_s=120) == set()


def test_watched_panes_without_a_tmux_server_is_empty(fake_tmux):
    fake_tmux.installed = False
    assert channels_mod.watched_panes() == set()


def test_channel_to_dict_carries_the_label(fake_tmux):
    payload = channels_mod.list_channels()[0].to_dict()
    assert payload["pane_id"] == "%0"
    assert payload["label"] == "◑ Roam Touch rebuild discussion"
