"""Runtime: the channel index, and who gets told the answer."""

import time

from nexus_voice.runtime import Delivery, NexusRuntime


class FakeHub:
    def __init__(self, channels=None, history=None):
        self._channels = channels or []
        self._history = history or {}
        self.sent = []

    async def channels(self):
        return self._channels

    async def history(self, pane_id, depth=12):
        return self._history.get(pane_id, [])

    async def send(self, pane_id, text):
        self.sent.append((pane_id, text))
        return {}


class FakeEmbedder:
    def __init__(self, vector=(1.0, 0.0)):
        self.vector = vector
        self.embedded = []

    async def embed(self, text, cache=False):
        self.embedded.append(text)
        return self.vector

    def forget(self, keep):
        pass


def build(channels=None, history=None):
    spoken = []

    async def speak(speaker, text):
        spoken.append((speaker, text))

    runtime = NexusRuntime(None, FakeHub(channels, history), FakeEmbedder(), speak)
    return runtime, spoken


CHANNELS = [
    {"pane_id": "%42", "label": "Gaggia Build", "live": True, "status": "idle", "cwd": "/Users/talos"},
    {"pane_id": "%9", "label": "Old dead thing", "live": False, "status": "dead", "cwd": ""},
]


class TestIndex:
    async def test_dead_channels_are_not_candidates(self):
        runtime, _ = build(CHANNELS)
        await runtime.refresh()
        panes = [c.pane_id for c in await runtime.candidates()]
        assert panes == ["%42"]

    async def test_document_is_label_plus_history(self):
        history = {"%42": [{"summary": "the OPV spring is 9 bar"},
                           {"summary": "silicone gaskets are fine"}]}
        runtime, _ = build(CHANNELS, history)
        await runtime.refresh()
        await runtime.candidates()
        doc = runtime._docs["%42"]
        assert "Gaggia Build" in doc and "OPV spring" in doc and "silicone" in doc

    async def test_duplicate_history_text_is_not_repeated(self):
        history = {"%42": [{"summary": "same"}, {"summary": "same"}]}
        runtime, _ = build(CHANNELS, history)
        await runtime.refresh()
        await runtime.candidates()
        assert runtime._docs["%42"].count("same") == 1


class TestDelivery:
    async def test_outcome_is_spoken_where_he_asked(self):
        runtime, spoken = build(CHANNELS)
        runtime.expect_answer("%42", "media_player.kitchen", "Gaggia Build")
        await runtime._on_frame({"event": {"kind": "outcome", "pane_id": "%42",
                                           "summary": "OPV set to 9 bar."}})
        assert spoken == [("media_player.kitchen", "OPV set to 9 bar.")]

    async def test_summary_is_spoken_not_the_body(self):
        # The body carries markdown, code fences and tables. The summary is
        # stripped and capped for exactly this path.
        runtime, spoken = build(CHANNELS)
        runtime.expect_answer("%42", "media_player.kitchen", "Gaggia Build")
        await runtime._on_frame({"event": {"kind": "outcome", "pane_id": "%42",
                                           "summary": "short spoken form",
                                           "body": "# Heading\n```py\ncode\n```"}})
        assert spoken[0][1] == "short spoken form"

    async def test_nothing_speaks_unasked(self):
        # ★★ The standing law: auto-speak was built once and killed inside an
        # hour. An outcome nobody asked for by voice makes NO sound.
        runtime, spoken = build(CHANNELS)
        await runtime._on_frame({"event": {"kind": "outcome", "pane_id": "%42",
                                           "summary": "unsolicited"}})
        assert spoken == []

    async def test_a_delivery_is_consumed_once(self):
        runtime, spoken = build(CHANNELS)
        runtime.expect_answer("%42", "media_player.kitchen", "Gaggia Build")
        frame = {"event": {"kind": "outcome", "pane_id": "%42", "summary": "one"}}
        await runtime._on_frame(frame)
        await runtime._on_frame(frame)
        assert len(spoken) == 1

    async def test_errors_are_spoken_too(self):
        runtime, spoken = build(CHANNELS)
        runtime.expect_answer("%42", "media_player.kitchen", "Gaggia Build")
        await runtime._on_frame({"event": {"kind": "error", "pane_id": "%42",
                                           "summary": "it failed"}})
        assert spoken[0][1] == "it failed"

    async def test_receipts_do_not_speak(self):
        runtime, spoken = build(CHANNELS)
        runtime.expect_answer("%42", "media_player.kitchen", "Gaggia Build")
        await runtime._on_frame({"event": {"kind": "receipt", "pane_id": "%42",
                                           "summary": "he just said this"}})
        assert spoken == []

    async def test_stale_delivery_is_dropped_silently(self):
        runtime, spoken = build(CHANNELS)
        runtime._pending["%42"] = Delivery("%42", "media_player.kitchen", "x",
                                           time.time() - 99999)
        await runtime._on_frame({"event": {"kind": "outcome", "pane_id": "%42",
                                           "summary": "hours too late"}})
        assert spoken == []

    async def test_no_speaker_means_no_delivery_recorded(self):
        runtime, spoken = build(CHANNELS)
        runtime.expect_answer("%42", "", "Gaggia Build")
        await runtime._on_frame({"event": {"kind": "outcome", "pane_id": "%42",
                                           "summary": "nowhere to say this"}})
        assert spoken == []


class TestFrames:
    async def test_channels_frame_replaces_the_index(self):
        runtime, _ = build(CHANNELS)
        await runtime.refresh()
        await runtime._on_frame({"type": "channels", "channels": [
            {"pane_id": "%7", "label": "New one", "live": True}]})
        assert list(runtime._channels) == ["%7"]

    async def test_traffic_marks_a_channel_document_stale(self):
        runtime, _ = build(CHANNELS)
        await runtime.refresh()
        await runtime.candidates()
        assert "%42" not in runtime._stale
        await runtime._on_frame({"event": {"kind": "receipt", "pane_id": "%42",
                                           "summary": "new talk"}})
        assert "%42" in runtime._stale

    async def test_junk_frames_are_ignored(self):
        runtime, spoken = build(CHANNELS)
        for frame in ({}, {"event": None}, {"event": "nope"}, {"type": "presence"}):
            await runtime._on_frame(frame)
        assert spoken == []
