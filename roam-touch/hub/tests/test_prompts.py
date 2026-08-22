"""Recognising an interactive selector on a pane, and choosing an option.

The captures below are REAL — taken off live panes on 2026-08-21 by spawning the
agents exactly as `channels.spawn` does. That matters more than usual here: the
whole module is pattern-matching against other people's TUIs, and a test written
from imagination would agree with a parser written from the same imagination.

⚠️ The failure mode is silence. A parser that recognises nothing looks identical to
a pane with no prompt, which is how the first version shipped blind to Codex.
"""

from __future__ import annotations

import pytest

import prompts

# Claude Code's trust gate, verbatim. Note "Security guide" sitting directly above
# the options: the nearest-line heuristic picks THAT as the question.
CLAUDE_TRUST = """\
────────────────────────────────────────────────────────────────────────────────
 Accessing workspace:
 /Users/talos
 Quick safety check: Is this a project you created or one you trust? (Like your
 own code, a well-known open source project, or work from your team). If not,
 take a moment to review what's in this folder first.
 Claude Code'll be able to read, edit, and execute files here.
 Security guide
 ❯ 1. Yes, I trust this folder
   2. No, exit
 Enter to confirm · Esc to cancel
"""

# Codex's update banner. Different cursor glyph — this is the one that was invisible.
CODEX_UPDATE = """\

  ✨ Update available! 0.147.0 -> 0.149.0

  Release notes: https://github.com/openai/codex/releases/latest

› 1. Update now (runs `npm install -g @openai/codex`)
  2. Skip
  3. Skip until next version

  Press enter to continue
"""

# A settled Claude prompt — no selector at all.
CLAUDE_IDLE = """\
 ▐▛███▛█   Claude Code v2.1.239
▝▜██████▀  Opus 5 · Claude Max
  ▝▝ ▝▝    /Users/talos
────────────────────────────────────────────────────────────────────────────────
❯ Try "create a util logging.py that..."
────────────────────────────────────────────────────────────────────────────────
  ⏵⏵ bypass permissions on (shift+tab to cycle)
"""


class TestDetection:
    def test_claude_trust_gate(self):
        p = prompts.parse(CLAUDE_TRUST)
        assert p is not None, "the gate that ate his first message"
        assert [o.n for o in p.options] == [1, 2]
        assert p.options[0].text == "Yes, I trust this folder"
        assert p.options[0].selected and not p.options[1].selected

    def test_the_question_is_the_block_not_the_nearest_line(self):
        p = prompts.parse(CLAUDE_TRUST)
        assert "Quick safety check" in p.question
        assert p.question != "Security guide", "the link label is not the question"

    def test_codex_update_menu_with_a_different_cursor_glyph(self):
        """› is not ❯. Hard-coding one made this menu invisible."""
        p = prompts.parse(CODEX_UPDATE)
        assert p is not None
        assert len(p.options) == 3
        assert p.options[0].selected
        assert "Update now" in p.options[0].text
        assert "0.149.0" in p.question

    def test_a_settled_prompt_is_not_a_selector(self):
        assert prompts.parse(CLAUDE_IDLE) is None

    def test_empty_screen(self):
        assert prompts.parse("") is None
        assert prompts.parse("\n\n") is None


class TestFalsePositives:
    """A false positive is worse than a miss: it queues his messages behind a
    prompt that does not exist."""

    def test_prose_with_a_numbered_list_is_not_a_menu(self):
        assert prompts.parse(
            "Here is what I did:\n"
            "1. read the file\n"
            "2. changed the constant\n"
            "3. ran the tests\n"
            "All green.\n"
        ) is None

    def test_a_numbered_list_split_across_paragraphs_is_prose(self):
        assert prompts.parse(
            "steps\n1. first\n\nsome commentary\n2. second\nEnter to confirm\n"
        ) is None

    def test_a_single_option_is_not_a_choice(self):
        assert prompts.parse("❯ 1. only one\nEnter to confirm\n") is None

    def test_options_must_start_at_one_and_run_in_order(self):
        assert prompts.parse("❯ 2. two\n  3. three\nEnter to confirm\n") is None

    def test_a_huge_numbered_list_is_not_a_menu(self):
        body = "\n".join(f"  {i}. item {i}" for i in range(1, 20))
        assert prompts.parse(body + "\nEnter to confirm\n") is None


class TestFingerprint:
    def test_moving_the_cursor_does_not_change_identity(self):
        """A menu repaints as the cursor moves; keying on the selection would
        emit a fresh prompt every time an arrow key was pressed at the keyboard."""
        moved = CLAUDE_TRUST.replace("❯ 1.", "  1.").replace("   2.", " ❯ 2.")
        a, b = prompts.parse(CLAUDE_TRUST), prompts.parse(moved)
        assert a and b
        assert a.fingerprint == b.fingerprint

    def test_a_different_menu_is_a_different_prompt(self):
        a, b = prompts.parse(CLAUDE_TRUST), prompts.parse(CODEX_UPDATE)
        assert a.fingerprint != b.fingerprint


class TestAnswering:
    def test_answers_with_the_digit_not_arrow_presses(self):
        p = prompts.parse(CODEX_UPDATE)
        assert prompts.answer_keys(p, 2) == ["2", "Enter"]

    def test_refuses_an_option_that_is_not_on_the_prompt(self):
        p = prompts.parse(CLAUDE_TRUST)
        with pytest.raises(ValueError):
            prompts.answer_keys(p, 3)
        with pytest.raises(ValueError):
            prompts.answer_keys(p, 0)

    def test_summary_says_what_is_being_asked(self):
        p = prompts.parse(CLAUDE_TRUST)
        assert "2 options" in p.summary()
