"""Reported presence -- the app saying "I am looking at the panel".

The last-input rule (test_api / test_bridge) decides almost everything now.
What is left here is the one case it cannot express: he is looking at the
panel without having sent anything.
"""

from __future__ import annotations

import pytest

from presence import DEFAULT_TTL_S, Presence, PresenceSource


class Clock:
    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def presence(clock) -> Presence:
    return Presence(clock=clock)


# ------------------------------------------------------------- the default


def test_nothing_known_means_push(presence):
    """⚠️ Absence of evidence is not presence. A missed message is worse."""
    assert presence.should_push("%0") is True
    assert presence.snapshot()["present"] is False


def test_a_source_that_covers_nothing_suppresses_nothing(presence):
    """Evidence he is at a keyboard is not evidence he can see this channel."""
    presence.report("some-desk-sensor", kind="input")
    assert presence.snapshot()["present"] is True
    assert presence.should_push("%0") is True


# ----------------------------------------------------------------- coverage


def test_a_reported_source_covers_only_its_panes(presence):
    presence.report("desk-panel", kind="app", panes=["%0"])
    assert presence.should_push("%0") is False
    assert presence.should_push("%1") is True


def test_the_app_foregrounded_covers_everything(presence):
    """The panel already shows what the notification would say."""
    presence.report("roam-app", kind="app", covers_all=True)
    assert presence.should_push("%0") is False
    assert presence.should_push("%99") is False
    assert presence.snapshot()["covers_all"] is True


def test_several_sources_union_their_coverage(presence):
    presence.report("roam-app", kind="app", panes=["%0"])
    presence.report("desk-panel", kind="app", panes=["%1"])
    assert presence.covered_panes() == {"%0", "%1"}
    assert presence.should_push("%2") is True


def test_covers_names_the_source_that_did_it(presence):
    presence.report("roam-app", kind="app", panes=["%0"])
    source = presence.covers("%0")
    assert source is not None and source.id == "roam-app"
    assert source.kind == "app"


# --------------------------------------------------------------------- ttl


def test_a_source_lapses_when_it_stops_refreshing(presence, clock):
    presence.report("roam-app", covers_all=True, ttl_s=30)
    assert presence.should_push("%0") is False
    clock.advance(31)
    assert presence.should_push("%0") is True, "silence must not be permanent"
    assert presence.snapshot()["present"] is False


def test_refreshing_keeps_it_alive_and_keeps_since(presence, clock):
    first = presence.report("roam-app", covers_all=True, ttl_s=30)
    clock.advance(20)
    again = presence.report("roam-app", covers_all=True, ttl_s=30)
    assert again.since == first.since, "one continuous visit, not a new one"
    clock.advance(20)
    assert presence.should_push("%0") is False


def test_a_lapsed_source_that_returns_starts_a_new_visit(presence, clock):
    first = presence.report("roam-app", covers_all=True, ttl_s=10)
    clock.advance(30)
    again = presence.report("roam-app", covers_all=True, ttl_s=10)
    assert again.since > first.since


def test_sweep_drops_only_the_expired(presence, clock):
    presence.report("a", covers_all=True, ttl_s=10)
    presence.report("b", covers_all=True, ttl_s=600)
    clock.advance(11)
    assert presence.sweep() == ["a"]
    assert [s.id for s in presence.live()] == ["b"]


def test_forget_is_immediate(presence):
    presence.report("roam-app", covers_all=True)
    assert presence.forget("roam-app") is True
    assert presence.should_push("%0") is True
    assert presence.forget("roam-app") is False


def test_a_source_needs_an_id(presence):
    with pytest.raises(ValueError):
        presence.report("")


# ---------------------------------------------------------------- snapshot


def test_snapshot_describes_the_situation(presence, clock):
    presence.report(
        "roam-app", kind="app", panes=["%0"], ttl_s=6, detail={"device": "pixel"}
    )
    clock.advance(2)
    snap = presence.snapshot()
    assert snap["present"] is True
    assert snap["covered_panes"] == ["%0"]
    source = snap["sources"][0]
    assert source["kind"] == "app"
    assert source["idle_s"] == 2.0
    assert source["expires_in_s"] == 4.0
    assert source["detail"]["device"] == "pixel"


def test_the_signature_ignores_timestamps(presence, clock):
    """Continuous typing must not become a firehose of presence frames."""
    presence.report("roam-app", kind="app", panes=["%0"], ttl_s=60)
    before = presence.signature()
    clock.advance(1)
    presence.report("roam-app", kind="app", panes=["%0"], ttl_s=60)
    assert presence.signature() == before
    presence.report("roam-app", kind="app", panes=["%1"], ttl_s=60)
    assert presence.signature() != before, "a real change still shows"


def test_signature_changes_when_a_source_lapses(presence, clock):
    presence.report("roam-app", covers_all=True, ttl_s=10)
    before = presence.signature()
    clock.advance(11)
    assert presence.signature() != before


def test_default_ttl_is_short_enough_to_lapse_but_long_enough_to_hold():
    assert 15 <= DEFAULT_TTL_S <= 300
