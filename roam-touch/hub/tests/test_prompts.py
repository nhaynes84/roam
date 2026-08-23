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

    def test_a_quoted_menu_scrolled_up_the_screen_is_not_live(self):
        """⚠️ THE false positive that actually happened: an agent WRITING ABOUT the
        trust dialog got announced as a real question, which would have queued his
        messages behind something nobody could answer. A live prompt waits for input
        at the BOTTOM; a quotation has output beneath it."""
        assert prompts.parse(
            "The channel it spawned is sitting at Claude's trust-folder dialog:\n"
            "  1. Yes, I trust this folder\n"
            "  2. No, exit\n"
            "Enter to confirm\n"
            "\n"
            "So the next thing to do is answer it, then carry on with the build.\n"
            "I will wait for you before touching anything else.\n"
            "Meanwhile the hub is up and the counters are reset.\n"
            "Let me know how you want to proceed.\n"
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


# The real thing, captured off a live pane 2026-08-23. THIS is what he actually meets,
# and the parser matched none of it for two days.
ASK_USER_QUESTION = """\
 \u2610 Indentation
Do you prefer tabs or spaces for indentation?
\u276f 1. Spaces
     Indent with space characters (most common default; width set per-language,
     e.g. 2 or 4).
  2. Tabs
     Indent with tab characters; each reader's editor renders the width they
     prefer.
  3. Type something.
\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
  4. Chat about this
Enter to select \u00b7 \u2191/\u2193 to navigate \u00b7 Esc to cancel
"""


class TestAskUserQuestion:
    """★ The picker he asked for: "when you format a series of tabbed questions for
    me to answer on a plan". Options are NOT contiguous — each carries a wrapped
    description, and a rule sits before the last one. Requiring consecutive lines is
    exactly why he never saw a prompt."""

    def test_it_is_detected_at_all(self):
        assert prompts.parse(ASK_USER_QUESTION) is not None

    def test_all_four_options_survive_their_descriptions(self):
        p = prompts.parse(ASK_USER_QUESTION)
        assert [o.n for o in p.options] == [1, 2, 3, 4]
        assert p.options[0].text == "Spaces"
        assert p.options[1].text == "Tabs"
        assert p.options[3].text == "Chat about this"

    def test_the_cursor_marks_the_default(self):
        p = prompts.parse(ASK_USER_QUESTION)
        assert p.options[0].selected and not p.options[1].selected

    def test_the_question_is_the_question(self):
        p = prompts.parse(ASK_USER_QUESTION)
        assert "tabs or spaces" in p.question

    def test_answering_picks_by_digit(self):
        p = prompts.parse(ASK_USER_QUESTION)
        assert prompts.answer_keys(p, 2) == ["2", "Enter"]


# A MULTI-question (tabbed) picker, captured live 2026-08-23 — the shape he actually
# gets when I ask several things at once, and the one that exposed the rule bug.
TABBED_PICKER = """\
 ☐ Theme

Light or dark theme?

❯ 1. Dark
     Dark background, light text.
  2. Light
     Light background, dark text.
  3. Type something.
────────────────────────────────────────────────────────────────────────────────
  4. Chat about this

Enter to select · ↑/↓ to navigate · Esc to cancel
"""


class TestTabbedPicker:
    def test_a_multi_question_picker_is_detected(self):
        assert prompts.parse(TABBED_PICKER) is not None

    def test_the_question_is_the_prompt_not_the_scrollback(self):
        """⚠️⚠️ `_clean` strips box-drawing characters as symbols, so a "────" rule
        came back EMPTY and read as a blank line. The question walk sailed past the
        top of the picker and returned whatever was in the scrollback — on a live
        pane it returned my own instruction to the agent. Rules are tested on the RAW
        line now, and the tab strip (☐ ✔ ← →) is a boundary too."""
        p = prompts.parse(TABBED_PICKER)
        assert "theme" in p.question.lower()
        assert "AskUserQuestion" not in p.question
        assert "\u2500" not in p.question

    def test_options_survive_their_descriptions_and_the_rule(self):
        p = prompts.parse(TABBED_PICKER)
        assert [o.n for o in p.options] == [1, 2, 3, 4]
