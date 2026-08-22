"""Matcher tests.

Fixtures are the REAL labels from the live hub on 2026-08-21, not invented
ones -- including their real `cwd` of `/Users/talos`, which is exactly why the
cwd signal must never be load-bearing.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))

from nexus_voice.matcher import (  # noqa: E402
    Candidate,
    cosine,
    keywords,
    match,
    normalize,
)

HOME = "/Users/talos"


def live_channels() -> list[Candidate]:
    return [
        Candidate("%1", "◑ Augment things", cwd=HOME),
        Candidate("%24", "◐ Roam Touch rebuild discussion", cwd=HOME),
        Candidate("%42", "Gaggia Build", cwd=HOME),
        Candidate("%45", "Home Automation", cwd=HOME),
    ]


class TestNormalize:
    def test_strips_punctuation_and_case(self):
        assert normalize("Gaggia  Build!") == "gaggia build"

    def test_keeps_status_glyphs_out_of_words(self):
        # The hub prefixes live labels with ◑/◐; they must not become tokens.
        assert keywords("◑ Augment things") == ["augment"]

    def test_filler_removed_but_short_labels_survive(self):
        # "The Cycle" is a real project; stripping "the" must leave "cycle",
        # never nothing.
        assert keywords("The Cycle") == ["cycle"]


class TestLexicalRouting:
    def test_exact_label(self):
        m = match("Home Automation", live_channels())
        assert m.routed and m.pane_id == "%45" and m.method == "exact"

    def test_spoken_phrasing_reaches_the_label(self):
        # "add this to the home automation notes" -> keywords {home, automation}
        m = match("the home automation notes", live_channels())
        assert m.routed and m.pane_id == "%45" and m.method == "subset"

    def test_single_distinctive_word(self):
        m = match("gaggia", live_channels())
        assert m.routed and m.pane_id == "%42"

    def test_label_glyphs_do_not_block_a_match(self):
        m = match("augment", live_channels())
        assert m.routed and m.pane_id == "%1"

    def test_unknown_project_spawns(self):
        m = match("the jeep brake booster", live_channels())
        assert m.kind == "spawn"

    def test_empty_utterance_spawns_rather_than_guessing(self):
        assert match("", live_channels()).kind == "spawn"


class TestDeadChannels:
    def test_dead_channel_is_never_a_target(self):
        chans = [Candidate("%9", "Home Automation", live=False)]
        assert match("home automation", chans).kind == "spawn"

    def test_live_duplicate_wins_over_dead_one(self):
        chans = [
            Candidate("%9", "Home Automation", live=False),
            Candidate("%45", "Home Automation", live=True),
        ]
        m = match("home automation", chans)
        assert m.routed and m.pane_id == "%45"

    def test_working_channel_is_still_a_valid_target(self):
        # It owes an outcome; that makes it busy, not wrong. The note belongs
        # in that conversation and the answer simply arrives later.
        chans = [Candidate("%42", "Gaggia Build", status="working")]
        assert match("gaggia build", chans).routed


class TestAmbiguity:
    def test_two_close_candidates_ask_instead_of_guessing(self):
        chans = [
            Candidate("%1", "Espresso Water"),
            Candidate("%2", "Espresso Grinder"),
        ]
        m = match("espresso", chans)
        assert m.kind == "ambiguous"
        assert set(m.alternatives) == {"Espresso Water", "Espresso Grinder"}

    def test_a_clear_winner_is_not_ambiguous(self):
        chans = [
            Candidate("%1", "Espresso Water"),
            Candidate("%2", "Autotrader"),
        ]
        assert match("espresso water", chans).routed


class TestSemanticLayer:
    """Vocabulary the words do not share -- 'espresso' -> 'Gaggia Build'."""

    def test_embedding_rescues_a_synonym(self):
        chans = [
            Candidate("%42", "Gaggia Build", vector=(1.0, 0.0, 0.0)),
            Candidate("%45", "Home Automation", vector=(0.0, 1.0, 0.0)),
        ]
        m = match("the espresso machine", chans, target_vector=(0.97, 0.05, 0.0))
        assert m.routed and m.pane_id == "%42" and m.method == "semantic"

    def test_semantic_never_outranks_an_exact_hit(self):
        chans = [
            Candidate("%42", "Gaggia Build", vector=(1.0, 0.0, 0.0)),
            Candidate("%45", "Home Automation", vector=(1.0, 0.0, 0.0)),
        ]
        m = match("home automation", chans, target_vector=(1.0, 0.0, 0.0))
        assert m.pane_id == "%45" and m.method == "exact"

    def test_weak_similarity_still_spawns(self):
        chans = [Candidate("%42", "Gaggia Build", vector=(1.0, 0.0, 0.0))]
        m = match("the jeep", chans, target_vector=(0.0, 0.0, 1.0))
        assert m.kind == "spawn"

    def test_missing_vectors_degrade_to_lexical_not_failure(self):
        # Ollama down: no target_vector. Lexical routing must still work.
        m = match("gaggia build", live_channels(), target_vector=None)
        assert m.routed and m.pane_id == "%42"


class TestCosine:
    @pytest.mark.parametrize(
        "a,b",
        [((), (1.0,)), ((0.0, 0.0), (1.0, 0.0)), ((1.0, 0.0), (1.0, 0.0, 0.0))],
    )
    def test_degenerate_inputs_score_zero_never_raise(self, a, b):
        assert cosine(a, b) == 0.0

    def test_identical_vectors(self):
        assert cosine((1.0, 2.0), (1.0, 2.0)) == pytest.approx(1.0)


class TestCwd:
    def test_cwd_breaks_a_tie(self):
        # Two identically-named channels: only the directory tells them apart.
        chans = [
            Candidate("%1", "Roaster notes", cwd="/Users/talos/Projects/liveroasted"),
            Candidate("%2", "Roaster notes", cwd=HOME),
        ]
        m = match("the liveroasted roaster", chans)
        assert m.routed and m.pane_id == "%1" and m.method.endswith("+cwd")

    def test_cwd_cannot_lift_a_no_match_over_the_floor(self):
        # The promise: breaks ties, decides nothing. An unrelated label in the
        # right directory is still an unrelated label.
        chans = [Candidate("%1", "Autotrader", cwd="/Users/talos/Projects/liveroasted")]
        assert match("liveroasted", chans).kind == "spawn"

    def test_ambiguous_when_both_tied_candidates_sit_in_the_directory(self):
        chans = [
            Candidate("%1", "Roaster notes", cwd="/Users/talos/Projects/liveroasted"),
            Candidate("%2", "Roaster notes", cwd="/Users/talos/Projects/liveroasted"),
        ]
        assert match("the liveroasted roaster", chans).kind == "ambiguous"

    def test_label_only_of_filler_words_is_still_routable(self):
        chans = [Candidate("%7", "Notes")]
        assert match("notes", chans).routed

    def test_home_cwd_is_inert(self):
        # The live-hub reality: every pane in $HOME. Must change nothing.
        m = match("talos", live_channels())
        assert m.kind == "spawn"


class TestSemanticMargin:
    """The measured rule: a confident embedding SEPARATES a leader from the
    field. A flat spread means "none of these", however high the top score."""

    def _chans(self, *vectors):
        names = ["Gaggia Build", "Home Automation", "Augment things"]
        return [Candidate(f"%{i}", n, vector=v)
                for i, (n, v) in enumerate(zip(names, vectors))]

    def test_flat_spread_spawns_even_when_scores_are_highish(self):
        # The real "jeep brake booster" shape: 0.422 / 0.418 / 0.406.
        chans = self._chans((1.0, 0.0), (0.999, 0.045), (0.998, 0.063))
        m = match("the jeep brake booster", chans, target_vector=(1.0, 0.0))
        assert m.kind == "spawn"

    def test_clear_leader_routes(self):
        chans = self._chans((1.0, 0.0), (0.2, 0.98), (0.1, 0.99))
        m = match("the espresso machine", chans, target_vector=(1.0, 0.0))
        assert m.routed and m.method == "semantic" and m.pane_id == "%0"

    def test_single_channel_abstains_from_semantic_routing(self):
        # No margin exists to measure; absolute cosine ranges overlap between
        # correct and incorrect matches, so the embedding must not decide.
        chans = [Candidate("%0", "Gaggia Build", vector=(1.0, 0.0))]
        assert match("the jeep", chans, target_vector=(0.99, 0.1)).kind == "spawn"

    def test_semantic_hit_never_beats_a_string_hit(self):
        chans = [
            Candidate("%0", "Gaggia Build", vector=(1.0, 0.0)),
            Candidate("%1", "Home Automation", vector=(0.0, 1.0)),
        ]
        m = match("home automation", chans, target_vector=(1.0, 0.0))
        assert m.pane_id == "%1" and m.method == "exact"
