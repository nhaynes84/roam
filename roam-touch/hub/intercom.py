"""Who is allowed to talk right now.

★ The owner's design, and it is the good one: *"i set one as 'Open channel, send
audio', and any other device can be set to 'Receiver' with the option to 'Talk to
Sender' which interrupts the received feed to push audio the other way with a PTT
type button."*

★★ WHY THAT SHAPE MATTERS. Because the receiver's PTT **interrupts** the feed rather
than joining it, only one direction is ever live. That means NO ECHO CANCELLATION --
the thing that actually sinks open-mic intercom, and the thing the Warble build has
been fighting from scratch. Half-duplex by construction beats full-duplex plus AEC.

⚠️ So the one invariant this module exists to hold: **exactly one party has the floor,
always.** Every bug worth fearing here is a violation of it -- two talkers means both
speakers are live in the same house and it howls; zero talkers means a monitor that
looks open and is silent.

The audio bytes never come through here. This is only the state machine, kept pure so
it is a test rather than a room with two laptops in it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

#: A talk burst nobody released -- a wedged client, a dropped socket mid-press, a
#: kid leaning on a button. Without this the channel stays seized forever and the
#: open mic he set up quietly stops working.
DEFAULT_TALK_TIMEOUT_S = 30.0

#: How long a sender may go missing before the channel is considered closed.
SENDER_STALE_S = 20.0


class IntercomError(Exception):
    """A request that cannot be honoured (no channel, floor taken)."""


@dataclass
class Intercom:
    """One open channel and whoever is currently holding the floor.

    `sender` is the device streaming by default. `talker` is None when the sender
    has the floor, or a receiver's id while that receiver is holding PTT.
    """

    sender: str | None = None
    talker: str | None = None
    receivers: dict[str, float] = field(default_factory=dict)
    #: device -> which lens it is showing ("back" | "front"). Not floor-governed.
    #: ⚠️ A MAP, not a set: a phone has two cameras and switching between them is a
    #: change of state, not an on/off.
    video: dict[str, str] = field(default_factory=dict)
    talk_started: float | None = None
    talk_timeout_s: float = DEFAULT_TALK_TIMEOUT_S
    sender_seen: float | None = None

    # ---------------------------------------------------------------- roles

    def open_channel(self, device: str, now: float | None = None) -> None:
        """Set `device` as the sender.

        ⚠️ A second device opening a channel TAKES OVER rather than being refused.
        Refusing looks identical to a bug from the new device's side, and the common
        real case is the same device reconnecting after a crash with a new socket --
        which would otherwise lock him out of his own intercom until a timeout.
        """
        now = time.monotonic() if now is None else now
        if self.sender is not None and self.sender != device:
            # the old sender loses the floor with the channel
            if self.talker == self.sender:
                self.talker = None
        self.sender = device
        self.sender_seen = now
        self.receivers.pop(device, None)
        if self.talker is None:
            self.talk_started = None

    def close_channel(self, device: str) -> None:
        """The sender stops. Any burst in flight dies with it."""
        if self.sender != device:
            return
        self.video.pop(device, None)
        self.sender = None
        self.sender_seen = None
        self.talker = None
        self.talk_started = None

    def join(self, device: str, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        if device == self.sender:
            return
        self.receivers[device] = now

    def leave(self, device: str) -> None:
        self.receivers.pop(device, None)
        # ⚠️ A camera must never outlive the socket that was showing it.
        self.video.pop(device, None)
        if self.talker == device:
            self.release(device)

    # ---------------------------------------------------------------- video

    def set_video(self, target: str, on: bool, by: str, facing: str = "back") -> None:
        """Turn a device's camera on or off.

        ★★ VIDEO IS NOT FLOOR-GOVERNED, and that is the whole point. Audio is
        half-duplex only because of echo; video has no echo, so the monitor keeps
        showing the room while someone talks back. His words: *"video in isolation
        does nothing for me, i can't lip read"* — so video always rides alongside
        audio, and the audio rules are untouched.

        ⚠️ THE ASYMMETRY IS DELIBERATE, and it is a privacy decision, not an
        oversight:
          * the SENDER's camera may be switched on by ANYONE — *"receiver can turn on
            sender video"*. That is the product: looking in on the room is the reason
            the channel exists.
          * a RECEIVER's own camera is theirs alone — *"Sender PTT is at sender
            discretion, they can toggle video on / off before a PTT event"*. Nobody
            gets to open a camera on the person who is merely listening.
        """
        if target != self.sender and target != by:
            raise IntercomError("only that device can turn on its own camera")
        if facing not in ("back", "front"):
            raise IntercomError(f"no such camera: {facing}")
        if on:
            self.video[target] = facing
        else:
            self.video.pop(target, None)

    def video_live(self, device: str) -> bool:
        return device in self.video

    def video_facing(self, device: str) -> str | None:
        return self.video.get(device)

    # ---------------------------------------------------------------- floor

    @property
    def is_open(self) -> bool:
        return self.sender is not None

    def holder(self) -> str | None:
        """Who the audio should currently be coming FROM."""
        if not self.is_open:
            return None
        return self.talker or self.sender

    def press(self, device: str, now: float | None = None) -> str:
        """A receiver holds Talk. Returns the device that now owns the floor.

        ⚠️ First press wins and a second is REFUSED, not queued. Two people talking
        at once is the one state that must never happen, and a queued burst arriving
        seconds later -- after its speaker has stopped talking -- is worse than being
        told no.
        """
        now = time.monotonic() if now is None else now
        self.expire(now)
        if not self.is_open:
            raise IntercomError("no open channel to talk to")
        if device == self.sender:
            raise IntercomError("the sender already has the floor")
        if self.talker is not None and self.talker != device:
            raise IntercomError(f"{self.talker} is already talking")
        self.talker = device
        self.talk_started = now
        self.receivers.setdefault(device, now)
        return device

    def release(self, device: str) -> str | None:
        """Let go of PTT. The sender's feed resumes."""
        if self.talker != device:
            return self.holder()
        self.talker = None
        self.talk_started = None
        return self.holder()

    def expire(self, now: float | None = None) -> bool:
        """Drop a talk burst nobody released. True if something was reclaimed."""
        now = time.monotonic() if now is None else now
        if self.talker is None or self.talk_started is None:
            return False
        if now - self.talk_started < self.talk_timeout_s:
            return False
        self.talker = None
        self.talk_started = None
        return True

    def touch_sender(self, now: float | None = None) -> None:
        self.sender_seen = time.monotonic() if now is None else now

    def sender_is_stale(self, now: float | None = None) -> bool:
        """A sender that stopped sending without saying so."""
        now = time.monotonic() if now is None else now
        if self.sender is None or self.sender_seen is None:
            return False
        return now - self.sender_seen > SENDER_STALE_S

    # ---------------------------------------------------------------- wire

    def snapshot(self) -> dict:
        """What every participant needs to render its own state.

        ★ `holder` is the single source of truth for "should I be playing, and should
        my mic be live". A client that decides for itself will eventually disagree
        with another client, and that disagreement is a howl.
        """
        return {
            "open": self.is_open,
            "sender": self.sender,
            "talker": self.talker,
            "holder": self.holder(),
            "receivers": sorted(self.receivers),
            "video": dict(self.video),
        }
