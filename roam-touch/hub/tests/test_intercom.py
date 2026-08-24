"""The floor: exactly one party talking, always.

Every test here is really the same test — that the invariant holds through whatever
sequence a house full of people and flaky sockets can produce. Two talkers means two
live speakers in the same building and it howls; zero talkers means a monitor that
looks open and is silent.
"""

from __future__ import annotations

import pytest

from intercom import Intercom, IntercomError


def opened(sender="kitchen", **kw) -> Intercom:
    ic = Intercom(**kw)
    ic.open_channel(sender, now=0.0)
    return ic


class TestOpening:
    def test_a_fresh_intercom_is_closed(self):
        ic = Intercom()
        assert not ic.is_open
        assert ic.holder() is None

    def test_the_sender_holds_the_floor_by_default(self):
        ic = opened()
        assert ic.is_open
        assert ic.holder() == "kitchen"
        assert ic.talker is None

    def test_a_second_sender_takes_over_rather_than_being_refused(self):
        """The common real case is the SAME device reconnecting after a crash.
        Refusing would lock him out of his own intercom until a timeout."""
        ic = opened()
        ic.open_channel("study", now=1.0)
        assert ic.sender == "study"
        assert ic.holder() == "study"

    def test_reopening_from_the_same_device_is_harmless(self):
        ic = opened()
        ic.open_channel("kitchen", now=1.0)
        assert ic.sender == "kitchen"
        assert ic.holder() == "kitchen"

    def test_closing_ends_the_channel_and_any_burst_in_flight(self):
        ic = opened()
        ic.join("desk", now=1.0)
        ic.press("desk", now=1.0)
        ic.close_channel("kitchen")
        assert not ic.is_open
        assert ic.holder() is None
        assert ic.talker is None

    def test_a_receiver_cannot_close_the_channel(self):
        ic = opened()
        ic.close_channel("desk")
        assert ic.is_open


class TestTalking:
    def test_ptt_interrupts_the_feed(self):
        """The heart of the design: talking takes the floor FROM the sender,
        rather than joining it. That is what removes the echo problem."""
        ic = opened()
        ic.join("desk", now=1.0)
        ic.press("desk", now=1.0)
        assert ic.holder() == "desk"
        assert ic.holder() != ic.sender

    def test_releasing_gives_it_back_to_the_sender(self):
        ic = opened()
        ic.press("desk", now=1.0)
        ic.release("desk")
        assert ic.holder() == "kitchen"

    def test_a_second_talker_is_refused_not_queued(self):
        """A queued burst arrives after its speaker has stopped talking, which is
        worse than being told no."""
        ic = opened()
        ic.press("desk", now=1.0)
        with pytest.raises(IntercomError):
            ic.press("phone", now=1.1)
        assert ic.holder() == "desk"

    def test_the_same_talker_pressing_twice_is_not_an_error(self):
        ic = opened()
        ic.press("desk", now=1.0)
        assert ic.press("desk", now=1.2) == "desk"

    def test_releasing_when_you_do_not_hold_it_changes_nothing(self):
        ic = opened()
        ic.press("desk", now=1.0)
        assert ic.release("phone") == "desk"
        assert ic.holder() == "desk"

    def test_the_sender_cannot_press_ptt(self):
        ic = opened()
        with pytest.raises(IntercomError):
            ic.press("kitchen", now=1.0)

    def test_talking_into_a_closed_channel_is_refused(self):
        ic = Intercom()
        with pytest.raises(IntercomError):
            ic.press("desk", now=1.0)


class TestStuckAndDropped:
    def test_a_burst_nobody_released_is_reclaimed(self):
        """A wedged client, a socket dropped mid-press, a kid leaning on a button.
        Without this the channel is seized forever and the monitor goes quiet."""
        ic = opened(talk_timeout_s=30.0)
        ic.press("desk", now=1.0)
        assert not ic.expire(now=20.0)
        assert ic.expire(now=40.0)
        assert ic.holder() == "kitchen"

    def test_a_talker_that_leaves_gives_the_floor_back(self):
        ic = opened()
        ic.join("desk", now=1.0)
        ic.press("desk", now=1.0)
        ic.leave("desk")
        assert ic.holder() == "kitchen"
        assert "desk" not in ic.receivers

    def test_pressing_reclaims_an_expired_burst_from_someone_else(self):
        ic = opened(talk_timeout_s=5.0)
        ic.press("desk", now=1.0)
        assert ic.press("phone", now=100.0) == "phone"

    def test_a_sender_that_stops_sending_reads_as_stale(self):
        ic = opened()
        ic.touch_sender(now=0.0)
        assert not ic.sender_is_stale(now=5.0)
        assert ic.sender_is_stale(now=100.0)

    def test_a_closed_channel_is_never_stale(self):
        assert not Intercom().sender_is_stale(now=10_000.0)


class TestSnapshot:
    def test_holder_is_the_single_source_of_truth(self):
        """A client that decides for itself will eventually disagree with another
        client, and that disagreement is a howl."""
        ic = opened()
        ic.join("desk", now=1.0)
        assert ic.snapshot()["holder"] == "kitchen"
        ic.press("desk", now=1.0)
        assert ic.snapshot()["holder"] == "desk"

    def test_snapshot_lists_receivers_without_the_sender(self):
        ic = opened()
        ic.join("desk", now=1.0)
        ic.join("kitchen", now=1.0)   # the sender is not its own receiver
        assert ic.snapshot()["receivers"] == ["desk"]


# ------------------------------------------------------------------ the relay

import json as _json                        # noqa: E402
from conftest import TOKEN                  # noqa: E402


def _ws(client, device, role="receiver"):
    return client.websocket_connect(
        f"/intercom?device={device}&role={role}&token={TOKEN}"
    )


def _floor(sock):
    """Next floor snapshot. Membership changes emit one per participant."""
    while True:
        msg = sock.receive()
        if msg.get("text"):
            data = _json.loads(msg["text"])
            if data.get("type") == "floor":
                return data


def _next_bytes(sock):
    """Next AUDIO frame, skipping control JSON.

    ⚠️ Every participant also receives floor snapshots, so a bare receive() lands
    on text and the test reads as a failure of the relay when it is a failure of
    the test.
    """
    while True:
        msg = sock.receive()
        if msg.get("bytes") is not None:
            return msg["bytes"]


def _floor_until(sock, holder, limit=12):
    """Wait for the floor to reach `holder`.

    ⚠️ Every membership change emits a snapshot to every participant, so a socket
    that has been open a while has several queued. Reading just the next one tests
    whichever event happened to be first, not the transition under test.
    """
    for _ in range(limit):
        snap = _floor(sock)
        if snap["holder"] == holder:
            return snap
    raise AssertionError(f"floor never reached {holder}")


def _until(sock, kind):
    while True:
        msg = sock.receive()
        if msg.get("text"):
            data = _json.loads(msg["text"])
            if data.get("type") == kind:
                return data


def test_a_receiver_hears_the_sender(client):
    with _ws(client, "kitchen", "sender") as tx, _ws(client, "desk") as rx:
        _floor(rx)
        tx.send_bytes(b"audioframe")
        assert _next_bytes(rx) == b"audioframe"


def test_audio_from_a_device_without_the_floor_is_dropped(client):
    """⚠️ THE test. A client is not trusted to stop sending when it loses the floor
    — a laggy release, a wedged press or an old build would otherwise put two live
    speakers in one house. The server decides whose bytes are relayed.

    Deterministic by construction: `phone` is listening to everything. If desk's
    audio were relayed it would arrive FIRST, so asserting on the first frame is
    enough — no timeouts, no sleeps.
    """
    with _ws(client, "kitchen", "sender") as tx, \
         _ws(client, "desk") as rx, _ws(client, "phone") as phone:
        _floor(phone)
        rx.send_bytes(b"should-not-arrive")   # desk does NOT hold the floor
        tx.send_bytes(b"from-the-sender")
        assert _next_bytes(phone) == b"from-the-sender"


def test_pressing_ptt_flips_the_direction(client):
    with _ws(client, "kitchen", "sender") as tx, _ws(client, "desk") as rx:
        _floor(rx)
        rx.send_text('{"type":"press"}')
        _floor_until(rx, "desk")      # PTT interrupts the feed
        rx.send_bytes(b"talking-back")
        assert _next_bytes(tx) == b"talking-back"


def test_the_sender_is_muted_while_a_receiver_talks(client):
    """The other half of half-duplex: the sender losing the floor must actually
    stop being relayed, or both directions are live and it howls."""
    with _ws(client, "kitchen", "sender") as tx, _ws(client, "desk") as rx:
        _floor(rx)
        rx.send_text('{"type":"press"}')
        _floor_until(rx, "desk")
        tx.send_bytes(b"sender-should-be-muted")
        rx.send_bytes(b"receiver-has-the-floor")
        assert _next_bytes(tx) == b"receiver-has-the-floor"


def test_a_denied_press_tells_the_client_why(client):
    with _ws(client, "kitchen", "sender") as tx, \
         _ws(client, "desk") as rx, _ws(client, "phone") as phone:
        _floor(rx)
        rx.send_text('{"type":"press"}')
        _floor(phone)
        phone.send_text('{"type":"press"}')
        assert "talking" in _until(phone, "denied")["detail"]


def test_the_floor_returns_to_the_sender_when_a_talker_disconnects(client):
    with _ws(client, "kitchen", "sender") as tx:
        with _ws(client, "desk") as rx:
            _floor(rx)
            rx.send_text('{"type":"press"}')
            _floor_until(tx, "desk")
        _floor_until(tx, "kitchen")   # a dropped talker frees the floor


class TestVideo:
    """★ "Streams should default to audio, but have the ability to turn on the video
    feed, from either end." Video rides alongside audio and is NOT floor-governed —
    audio is half-duplex only because of echo, and video has none."""

    def test_video_is_off_until_asked_for(self):
        ic = opened()
        assert not ic.video_live("kitchen")
        assert ic.snapshot()["video"] == {}

    def test_a_receiver_may_turn_on_the_senders_camera(self):
        """The product: looking in on the room is why the channel exists."""
        ic = opened()
        ic.join("desk", now=1.0)
        ic.set_video("kitchen", True, by="desk")
        assert ic.video_live("kitchen")

    def test_the_sender_may_turn_on_its_own_camera(self):
        ic = opened()
        ic.set_video("kitchen", True, by="kitchen")
        assert ic.video_live("kitchen")

    def test_nobody_may_open_a_camera_on_a_listener(self):
        """⚠️ The asymmetry is the privacy decision. A receiver's camera is theirs."""
        ic = opened()
        ic.join("desk", now=1.0)
        ic.join("phone", now=1.0)
        with pytest.raises(IntercomError):
            ic.set_video("desk", True, by="phone")
        with pytest.raises(IntercomError):
            ic.set_video("desk", True, by="kitchen")
        assert not ic.video_live("desk")

    def test_a_listener_may_turn_on_their_own_camera_to_talk_back(self):
        ic = opened()
        ic.join("desk", now=1.0)
        ic.set_video("desk", True, by="desk")
        assert ic.video_live("desk")

    def test_video_does_not_follow_the_floor(self):
        """The room stays visible while someone talks back — that is the point."""
        ic = opened()
        ic.join("desk", now=1.0)
        ic.set_video("kitchen", True, by="desk")
        ic.press("desk", now=1.0)
        assert ic.holder() == "desk"
        assert ic.video_live("kitchen"), "the monitor must not go dark to talk to it"

    def test_a_camera_never_outlives_its_socket(self):
        ic = opened()
        ic.join("desk", now=1.0)
        ic.set_video("desk", True, by="desk")
        ic.leave("desk")
        assert not ic.video_live("desk")

    def test_closing_the_channel_kills_the_senders_camera(self):
        ic = opened()
        ic.set_video("kitchen", True, by="kitchen")
        ic.close_channel("kitchen")
        assert not ic.video_live("kitchen")
        assert ic.snapshot()["video"] == {}


def _vws(client, device):
    return client.websocket_connect(f"/intercom/video?device={device}&token={TOKEN}")


def test_video_frames_reach_listeners_when_the_camera_is_on(client):
    with _ws(client, "kitchen", "sender") as tx, _ws(client, "desk") as rx:
        _floor(rx)
        rx.send_text('{"type":"video","target":"kitchen","on":true}')
        _floor_until(rx, "kitchen")
        with _vws(client, "kitchen") as vtx, _vws(client, "desk") as vrx:
            vtx.send_bytes(b"JPEGFRAME")
            assert vrx.receive()["bytes"] == b"JPEGFRAME"


def test_video_from_a_camera_that_was_switched_off_is_dropped(client):
    """⚠️ Same rule as audio: the SERVER decides whether the bytes travel. A client
    told to stop is not trusted to stop, and a picture arriving after the camera was
    turned off is the failure that matters."""
    with _ws(client, "kitchen", "sender") as tx, _ws(client, "desk") as rx:
        _floor(rx)
        with _vws(client, "kitchen") as vtx, _vws(client, "desk") as vrx:
            vtx.send_bytes(b"SHOULD-NOT-TRAVEL")     # camera never enabled
            rx.send_text('{"type":"video","target":"kitchen","on":true}')
            _floor_until(rx, "kitchen")
            vtx.send_bytes(b"NOW-ALLOWED")
            assert vrx.receive()["bytes"] == b"NOW-ALLOWED"


def test_the_picture_survives_a_ptt_burst(client):
    """★ Video is not floor-governed: the room stays visible while you talk to it."""
    with _ws(client, "kitchen", "sender") as tx, _ws(client, "desk") as rx:
        _floor(rx)
        rx.send_text('{"type":"video","target":"kitchen","on":true}')
        _floor_until(rx, "kitchen")
        rx.send_text('{"type":"press"}')
        _floor_until(rx, "desk")
        with _vws(client, "kitchen") as vtx, _vws(client, "desk") as vrx:
            vtx.send_bytes(b"STILL-WATCHING")
            assert vrx.receive()["bytes"] == b"STILL-WATCHING"


def test_a_listener_cannot_open_a_camera_on_another_listener(client):
    with _ws(client, "kitchen", "sender") as tx, \
         _ws(client, "desk") as rx, _ws(client, "phone") as phone:
        _floor(phone)
        phone.send_text('{"type":"video","target":"desk","on":true}')
        assert "own camera" in _until(phone, "denied")["detail"]


class TestCameraSelection:
    """★ "phones have 2 cams, should be selectable, same rules, receiver can select
    sender cam option; receiver can set / change their own cam"."""

    def test_the_lens_is_part_of_the_state_not_just_on_or_off(self):
        ic = opened()
        ic.set_video("kitchen", True, by="kitchen", facing="front")
        assert ic.video_facing("kitchen") == "front"
        assert ic.snapshot()["video"] == {"kitchen": "front"}

    def test_a_receiver_may_switch_which_lens_the_sender_shows(self):
        ic = opened()
        ic.join("desk", now=1.0)
        ic.set_video("kitchen", True, by="desk", facing="back")
        ic.set_video("kitchen", True, by="desk", facing="front")
        assert ic.video_facing("kitchen") == "front", "switching lens is a state change"

    def test_a_listener_still_cannot_point_someone_elses_camera(self):
        ic = opened()
        ic.join("desk", now=1.0)
        ic.join("phone", now=1.0)
        with pytest.raises(IntercomError):
            ic.set_video("desk", True, by="phone", facing="front")

    def test_an_unknown_lens_is_refused(self):
        ic = opened()
        with pytest.raises(IntercomError):
            ic.set_video("kitchen", True, by="kitchen", facing="periscope")

    def test_turning_it_off_forgets_the_lens(self):
        ic = opened()
        ic.set_video("kitchen", True, by="kitchen", facing="front")
        ic.set_video("kitchen", False, by="kitchen")
        assert ic.video_facing("kitchen") is None


class TestListenerVideoIsABurst:
    """★ "once i enable video as the PTT option as a receiver, it shows it non stop;
    not just when sending." The sender IS the monitor and is continuous; a listener's
    camera is the other half of a talk-back and belongs to the burst."""

    def test_the_senders_camera_is_continuous(self):
        ic = opened()
        ic.set_video("kitchen", True, by="kitchen")
        assert ic.video_should_relay("kitchen")

    def test_a_listeners_camera_is_dark_until_they_hold_the_floor(self):
        ic = opened()
        ic.join("desk", now=1.0)
        ic.set_video("desk", True, by="desk")
        assert not ic.video_should_relay("desk"), "enabling is arming, not broadcasting"
        ic.press("desk", now=1.0)
        assert ic.video_should_relay("desk")
        ic.release("desk")
        assert not ic.video_should_relay("desk"), "dark the moment they let go"

    def test_the_monitor_keeps_showing_while_someone_talks_back(self):
        ic = opened()
        ic.join("desk", now=1.0)
        ic.set_video("kitchen", True, by="desk")
        ic.set_video("desk", True, by="desk")
        ic.press("desk", now=1.0)
        assert ic.video_should_relay("kitchen"), "the room must not go dark"
        assert ic.video_should_relay("desk")

    def test_a_camera_that_was_never_enabled_never_relays(self):
        ic = opened()
        ic.join("desk", now=1.0)
        ic.press("desk", now=1.0)
        assert not ic.video_should_relay("desk")
