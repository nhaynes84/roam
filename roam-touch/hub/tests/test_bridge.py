"""hub -> phone bridge. Faked at both boundaries: `roam-msg` (the subprocess)
and the hub socket (frames are handed straight to the handler).

The rules under test are the ones that decide whether someone keeps wearing
the thing: the right label, no echo of what he just typed, and no buzz about
the screen he is already looking at.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

import bridge as bridge_mod
from bridge import PUSH_KINDS, Bridge, Settings, State, compose, trim


def settings_for(tmp_path: Path, **overrides) -> Settings:
    base = dict(
        token="t",
        state_file=tmp_path / "state.json",
        min_interval_s=0.0,
        suppress_when_present=True,
        roam_msg=tmp_path / "roam-msg",
    )
    base.update(overrides)
    return Settings(**base)


class FakePhone:
    """Stands in for `roam-msg`."""

    def __init__(self, ok: bool = True) -> None:
        self.messages: list[tuple[str, str]] = []
        self.ok = ok

    async def __call__(self, text: str, pane_id: str) -> bool:
        self.messages.append((pane_id, text))
        return self.ok


class FakeClock:
    """Time the test controls, so rate limiting is asserted, not slept through."""

    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def make_bridge(tmp_path, watched=(), phone=None, clock=None, covers_all=False, **overrides):
    """`watched` is what the HUB says he can see -- the bridge never asks tmux."""
    phone = phone or FakePhone()
    bridge = Bridge(settings_for(tmp_path, **overrides), pusher=phone, clock=clock)
    bridge.labels = {"%0": "◑ Roam Touch rebuild discussion", "%1": "✳ Augment things"}
    if watched or covers_all:
        bridge.presence = {
            "present": True,
            "covers_all": covers_all,
            "covered_panes": list(watched),
            "sources": [],
        }
    return bridge, phone


def event(event_id: int, kind: str = "outcome", pane: str = "%1", **extra) -> dict:
    payload = {
        "id": event_id,
        "pane_id": pane,
        "kind": kind,
        "body": "the long body",
        "summary": "the suite is green — 122 tests",
        "meta": {},
        "ts": 1786515000.0,
    }
    payload.update(extra)
    return payload


# ----------------------------------------------------------------- policy


@pytest.mark.asyncio
async def test_an_outcome_is_pushed_with_the_channel_label(tmp_path):
    """The label is the point: which session is talking, without unlocking."""
    bridge, phone = make_bridge(tmp_path)
    await bridge.handle_event(event(10))
    assert phone.messages == [
        ("%1", "✳ Augment things: the suite is green — 122 tests")
    ]


@pytest.mark.asyncio
async def test_an_error_is_pushed_and_marked(tmp_path):
    bridge, phone = make_bridge(tmp_path)
    await bridge.handle_event(event(11, kind="error", summary="tmux refused the send"))
    assert phone.messages[0][1].startswith("⚠️ ✳ Augment things:")


@pytest.mark.asyncio
async def test_a_receipt_is_never_pushed(tmp_path):
    """He typed it seconds ago. Echoing it to his arm is noise."""
    bridge, phone = make_bridge(tmp_path)
    await bridge.handle_event(event(12, kind="receipt", summary="run the tests"))
    assert phone.messages == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["sent", "opened", "closed", "note", "receipt"])
async def test_bookkeeping_kinds_are_not_pushed(tmp_path, kind):
    bridge, phone = make_bridge(tmp_path)
    await bridge.handle_event(event(13, kind=kind))
    assert phone.messages == []
    assert kind not in PUSH_KINDS


@pytest.mark.asyncio
async def test_the_pane_he_is_sitting_in_is_suppressed(tmp_path):
    """No buzz for the message appearing on the screen in front of him."""
    bridge, phone = make_bridge(tmp_path, watched=["%1"])
    await bridge.handle_event(event(14, pane="%1"))
    assert phone.messages == []
    assert bridge.suppressed == 1


@pytest.mark.asyncio
async def test_another_pane_still_gets_through_while_he_watches_one(tmp_path):
    bridge, phone = make_bridge(tmp_path, watched=["%0"])
    await bridge.handle_event(event(15, pane="%1"))
    assert [p for p, _ in phone.messages] == ["%1"]


@pytest.mark.asyncio
async def test_suppression_can_be_disabled(tmp_path):
    bridge, phone = make_bridge(tmp_path, watched=["%1"], suppress_when_present=False)
    await bridge.handle_event(event(16, pane="%1"))
    assert len(phone.messages) == 1


@pytest.mark.asyncio
async def test_no_presence_information_means_push(tmp_path):
    """A hub too old to report presence, or a bridge that just started."""
    phone = FakePhone()
    bridge = Bridge(settings_for(tmp_path), pusher=phone)
    assert bridge.presence == {}
    await bridge.handle_event(event(17))
    assert len(phone.messages) == 1, "unknown must never mean silence"


@pytest.mark.asyncio
async def test_an_unknown_pane_falls_back_to_its_id(tmp_path):
    bridge, phone = make_bridge(tmp_path)
    await bridge.handle_event(event(18, pane="%7"))
    assert phone.messages[0][1].startswith("%7: ")


@pytest.mark.asyncio
async def test_the_app_being_foregrounded_silences_every_channel(tmp_path):
    """The panel already shows it. This is the ROAM app's own presence report."""
    bridge, phone = make_bridge(tmp_path, covers_all=True)
    await bridge.handle_event(event(19, pane="%1"))
    await bridge.handle_event(event(20, pane="%0"))
    assert phone.messages == []
    assert bridge.suppressed == 2


@pytest.mark.asyncio
async def test_presence_arrives_over_the_socket_and_takes_effect(tmp_path):
    bridge, phone = make_bridge(tmp_path)
    await bridge.handle_event(event(21, pane="%1"))
    assert len(phone.messages) == 1, "nothing known yet: push"
    await bridge.handle_frame(
        {
            "type": "presence",
            "present": True,
            "covers_all": False,
            "covered_panes": ["%1"],
            "sources": [{"id": "tmux:/dev/ttys000", "kind": "tmux"}],
        }
    )
    await bridge.handle_event(event(22, pane="%1"))
    assert len(phone.messages) == 1, "he sat down in that pane; stop buzzing"


@pytest.mark.asyncio
async def test_presence_in_hello_is_honoured_immediately(tmp_path):
    bridge, phone = make_bridge(tmp_path)
    await bridge.handle_frame(
        {
            "type": "hello",
            "latest_event_id": 0,
            "channels": [],
            "presence": {"present": True, "covers_all": True, "covered_panes": []},
        }
    )
    await bridge.handle_event(event(23))
    assert phone.messages == []


@pytest.mark.asyncio
async def test_when_he_walks_away_the_channel_starts_pushing_again(tmp_path):
    bridge, phone = make_bridge(tmp_path, watched=["%1"])
    await bridge.handle_event(event(24, pane="%1"))
    assert phone.messages == []
    await bridge.handle_frame(
        {"type": "presence", "present": False, "covers_all": False, "covered_panes": []}
    )
    await bridge.handle_event(event(25, pane="%1"))
    assert len(phone.messages) == 1


# ---------------------------------------------------- the boxed backlog


@pytest.mark.asyncio
async def test_a_small_backlog_is_delivered(tmp_path):
    bridge, phone = make_bridge(tmp_path, min_interval_s=0.0)
    bridge.state.remember(100)
    await bridge.handle_frame(
        {
            "type": "backlog",
            "events": [event(n, pane=f"%{n}") for n in range(101, 104)],
        }
    )
    assert len(phone.messages) == 3
    assert bridge.skipped_backlogs == 0


@pytest.mark.asyncio
async def test_a_big_backlog_stays_quiet_and_still_advances(tmp_path):
    """15+ behind means he was working elsewhere and has already seen it."""
    bridge, phone = make_bridge(tmp_path, min_interval_s=0.0)
    bridge.state.remember(100)
    missed = [event(n, pane=f"%{n}") for n in range(101, 121)]  # 20 outcomes
    await bridge.handle_frame({"type": "backlog", "events": missed})
    assert phone.messages == [], "no ping; they are in the channels"
    assert bridge.state.last_event_id == 120, "but we are caught up"
    assert bridge.skipped_backlogs == 1


@pytest.mark.asyncio
async def test_the_boxing_counts_only_what_would_ping(tmp_path):
    """Twenty events, three of which are pushable, is not a big backlog."""
    bridge, phone = make_bridge(tmp_path, min_interval_s=0.0)
    bridge.state.remember(200)
    events = [event(n, kind="sent", pane="%1") for n in range(201, 218)]
    events += [event(n, kind="outcome", pane=f"%{n}") for n in range(218, 221)]
    await bridge.handle_frame({"type": "backlog", "events": events})
    assert len(phone.messages) == 3
    assert bridge.skipped_backlogs == 0


@pytest.mark.asyncio
async def test_the_backlog_limit_is_configurable(tmp_path):
    bridge, phone = make_bridge(tmp_path, min_interval_s=0.0, backlog_push_limit=2)
    bridge.state.remember(300)
    await bridge.handle_frame(
        {"type": "backlog", "events": [event(n, pane=f"%{n}") for n in range(301, 305)]}
    )
    assert phone.messages == []
    assert bridge.state.last_event_id == 304


@pytest.mark.asyncio
async def test_already_seen_events_do_not_count_towards_the_limit(tmp_path):
    """A replayed backlog after a reconnect is not 'being behind'."""
    bridge, phone = make_bridge(tmp_path, min_interval_s=0.0, backlog_push_limit=3)
    bridge.state.remember(420)
    old = [event(n, pane=f"%{n}") for n in range(400, 421)]
    fresh = [event(421, pane="%1")]
    await bridge.handle_frame({"type": "backlog", "events": old + fresh})
    assert len(phone.messages) == 1
    assert bridge.skipped_backlogs == 0


# ------------------------------------------------------- rate and coalescing


@pytest.mark.asyncio
async def test_a_burst_is_coalesced_per_channel(tmp_path):
    """Five outcomes in a second must not be five buzzes."""
    clock = FakeClock()
    bridge, phone = make_bridge(tmp_path, min_interval_s=60.0, clock=clock)
    for n in range(20, 25):
        await bridge.handle_event(event(n, pane="%1", summary=f"answer {n}"))
    assert len(phone.messages) == 1, "one push, the rest coalesced"
    assert "answer 20" in phone.messages[0][1]
    await bridge.drain()
    assert len(phone.messages) == 1, "still inside the rate-limit window"
    clock.advance(61)
    await bridge.drain()
    assert len(phone.messages) == 2
    assert "answer 24" in phone.messages[1][1], "the newest survives"
    assert "(+3 more)" in phone.messages[1][1]


@pytest.mark.asyncio
async def test_the_rate_limit_spaces_pushes(tmp_path):
    clock = FakeClock()
    bridge, phone = make_bridge(tmp_path, min_interval_s=30.0, clock=clock)
    await bridge.handle_event(event(30, pane="%0"))
    await bridge.handle_event(event(31, pane="%1"))
    assert len(phone.messages) == 1
    clock.advance(31)
    await bridge.drain()
    assert len(phone.messages) == 2
    assert {p for p, _ in phone.messages} == {"%0", "%1"}


@pytest.mark.asyncio
async def test_the_queue_cannot_grow_without_bound(tmp_path):
    bridge, phone = make_bridge(tmp_path, min_interval_s=60.0, max_queued_channels=3)
    for n in range(40, 50):
        await bridge.handle_event(event(n, pane=f"%{n}"))
    assert len(bridge._queue) <= 3


@pytest.mark.asyncio
async def test_a_failed_push_does_not_stop_the_bridge(tmp_path):
    clock = FakeClock()
    phone = FakePhone(ok=False)
    bridge, _ = make_bridge(tmp_path, phone=phone, clock=clock, offline_backoff_s=0.0)
    await bridge.handle_event(event(50))
    await bridge.handle_event(event(51))
    assert len(phone.messages) >= 2
    assert bridge.state.last_event_id == 51, "the cursor still advances"


@pytest.mark.asyncio
async def test_an_unreachable_phone_is_retried_once_then_dropped(tmp_path):
    """`roam-msg` blocks ~75 s on a sleeping phone; do not keep paying that."""
    clock = FakeClock()
    phone = FakePhone(ok=False)
    bridge, _ = make_bridge(tmp_path, phone=phone, clock=clock, offline_backoff_s=60.0)
    await bridge.handle_event(event(52, summary="the answer"))
    assert len(phone.messages) == 1
    assert bridge._queue, "kept for one retry"

    await bridge.drain()
    assert len(phone.messages) == 1, "backoff: no hammering while it is offline"

    clock.advance(61)
    await bridge.drain()
    assert len(phone.messages) == 2, "one retry after the backoff"
    assert not bridge._queue and bridge.dropped == 1


@pytest.mark.asyncio
async def test_a_phone_that_comes_back_gets_the_retry(tmp_path):
    clock = FakeClock()
    phone = FakePhone(ok=False)
    bridge, _ = make_bridge(tmp_path, phone=phone, clock=clock, offline_backoff_s=10.0)
    await bridge.handle_event(event(53, summary="landed late"))
    phone.ok = True
    clock.advance(11)
    await bridge.drain()
    assert len(phone.messages) == 2
    assert bridge.dropped == 0
    assert "landed late" in phone.messages[-1][1]


@pytest.mark.asyncio
async def test_events_keep_being_recorded_while_the_phone_is_offline(tmp_path):
    """A dead push path must never stall the cursor or the socket."""
    clock = FakeClock()
    phone = FakePhone(ok=False)
    bridge, _ = make_bridge(tmp_path, phone=phone, clock=clock)
    for n in range(54, 60):
        await bridge.handle_event(event(n, pane=f"%{n}"))
    assert bridge.state.last_event_id == 59
    assert len(phone.messages) == 1, "one attempt, then backoff"


# ------------------------------------------------------------------ cursor


@pytest.mark.asyncio
async def test_the_cursor_is_persisted_and_reused(tmp_path):
    bridge, _ = make_bridge(tmp_path)
    await bridge.handle_event(event(60))
    saved = json.loads((tmp_path / "state.json").read_text())
    assert saved == {"last_event_id": 60}
    resumed = State(tmp_path / "state.json")
    assert resumed.last_event_id == 60


@pytest.mark.asyncio
async def test_events_already_seen_are_not_pushed_again(tmp_path):
    """A reconnect replays the backlog; the phone must not buzz twice."""
    bridge, phone = make_bridge(tmp_path)
    await bridge.handle_event(event(70))
    await bridge.handle_frame({"type": "backlog", "events": [event(70), event(71)]})
    assert [p for p, _ in phone.messages] == ["%1", "%1"]
    assert bridge.state.last_event_id == 71


@pytest.mark.asyncio
async def test_a_first_ever_run_does_not_replay_history(tmp_path):
    """Nobody wants a week of old outcomes on their arm at startup."""
    bridge, phone = make_bridge(tmp_path)
    assert bridge.state.last_event_id is None
    await bridge.handle_frame(
        {"type": "hello", "latest_event_id": 500, "channels": []}
    )
    assert bridge.state.last_event_id == 500
    await bridge.handle_frame({"type": "backlog", "events": [event(499)]})
    assert phone.messages == []


@pytest.mark.asyncio
async def test_a_restart_resumes_from_the_stored_cursor(tmp_path):
    (tmp_path / "state.json").write_text(json.dumps({"last_event_id": 200}))
    bridge, phone = make_bridge(tmp_path)
    assert bridge.ws_url().endswith("/ws?since=200")
    await bridge.handle_frame(
        {"type": "hello", "latest_event_id": 900, "channels": []}
    )
    assert bridge.state.last_event_id == 200, "hello must not skip what we missed"
    await bridge.handle_frame({"type": "backlog", "events": [event(201)]})
    assert len(phone.messages) == 1


def test_a_corrupt_state_file_is_treated_as_a_first_run(tmp_path):
    (tmp_path / "state.json").write_text("{not json")
    assert State(tmp_path / "state.json").last_event_id is None


def test_the_url_has_no_since_on_a_first_run(tmp_path):
    bridge, _ = make_bridge(tmp_path)
    assert bridge.ws_url().endswith("/ws")


def test_the_url_is_websocket_scheme(tmp_path):
    bridge, _ = make_bridge(tmp_path, hub_url="http://talos:8787/")
    assert bridge.ws_url().startswith("ws://talos:8787/ws")


# ------------------------------------------------------------------ labels


@pytest.mark.asyncio
async def test_labels_track_the_hub(tmp_path):
    bridge, phone = make_bridge(tmp_path)
    await bridge.handle_frame(
        {
            "type": "channels",
            "channels": [{"pane_id": "%1", "label": "✳ Renamed session"}],
        }
    )
    await bridge.handle_event(event(80, pane="%1"))
    assert phone.messages[0][1].startswith("✳ Renamed session:")


@pytest.mark.asyncio
async def test_a_single_channel_frame_updates_one_label(tmp_path):
    bridge, _ = make_bridge(tmp_path)
    await bridge.handle_frame(
        {"type": "channel", "channel": {"pane_id": "%1", "label": "new name"}}
    )
    assert bridge.label_for("%1") == "new name"


@pytest.mark.asyncio
async def test_unknown_frames_are_ignored(tmp_path):
    bridge, phone = make_bridge(tmp_path)
    for frame in ({"type": "ping"}, {"type": "desync"}, {"type": "wat"}, {}):
        await bridge.handle_frame(frame)
    assert phone.messages == []


# ---------------------------------------------------------------- composing


def test_a_long_answer_is_trimmed_for_a_phone_notification():
    text = compose("✳ Augment things", "x" * 400, "outcome", summary_chars=120)
    assert len(text) <= 32 + 2 + 120 + 1
    assert text.endswith("…")


def test_a_long_label_is_trimmed_too():
    text = compose("a very long session title " * 3, "done", "outcome", label_chars=20)
    assert text.startswith("a very long session…")


def test_whitespace_is_flattened_for_the_strip():
    assert trim("one\n\n  two   three", 40) == "one two three"


def test_compose_survives_missing_pieces():
    assert compose("", "", "outcome") == "channel:"
