"""Turning what he said into a prompt and a channel name.

Lives apart from `conversation.py` so it can be tested without Home Assistant
installed -- the agent module imports `homeassistant.*` at module scope, which
makes everything in it untestable on a dev box. Logic does not belong there.
"""

from __future__ import annotations

from .const import TRIGGER_WORD
from .matcher import normalize


def strip_trigger(text: str) -> str:
    """Drop a leading "Nexus," so the trigger word never reaches the agent.

    Prefix routing rather than intent classification: "kitchen lights off" can
    then never be misread as something to send to Claude, and "Nexus, add a
    note" can never be eaten by a local intent. The two lanes stay separate by
    construction, which is the entire point of the split.
    """
    stripped = text.strip()
    words = normalize(stripped).split()
    if words and words[0] == TRIGGER_WORD:
        # Cut from the ORIGINAL string so casing and punctuation in the
        # remainder survive untouched -- the prompt is passed on verbatim.
        idx = stripped.lower().find(TRIGGER_WORD) + len(TRIGGER_WORD)
        return stripped[idx:].lstrip(" ,.:-").strip()
    return stripped


def label_for(text: str) -> str:
    """A channel name from what he said. Short: it becomes a tmux pane title."""
    return " ".join(text.split()[:6])[:48] or "voice"
