"""Trigger-word stripping and channel naming."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))

from nexus_voice.phrasing import label_for, strip_trigger  # noqa: E402


class TestStripTrigger:
    def test_removes_leading_trigger_and_comma(self):
        assert strip_trigger("Nexus, add a note to the espresso project") == (
            "add a note to the espresso project"
        )

    def test_case_insensitive(self):
        assert strip_trigger("NEXUS add the thing") == "add the thing"

    def test_preserves_casing_and_punctuation_of_the_remainder(self):
        # The prompt is passed to Claude verbatim -- mangling it would change
        # what he actually asked.
        assert strip_trigger("nexus: Check the OPV at 9.5 bar, then report.") == (
            "Check the OPV at 9.5 bar, then report."
        )

    def test_trigger_word_inside_the_sentence_is_left_alone(self):
        # He may well be talking ABOUT Nexus; only a leading one routes.
        text = "tell me about the nexus build"
        assert strip_trigger(text) == text

    def test_bare_trigger_yields_empty(self):
        assert strip_trigger("Nexus") == ""
        assert strip_trigger("  nexus,  ") == ""


class TestLabelFor:
    def test_first_words_become_the_label(self):
        assert label_for("add the OPV result to the espresso notes") == (
            "add the OPV result to the"
        )

    def test_capped_in_length(self):
        assert len(label_for("word " * 40)) <= 48

    def test_empty_text_still_names_the_channel(self):
        # A pane with no title reads as the hostname, so it must never be "".
        assert label_for("") == "voice"
