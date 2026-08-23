"""Lift an interactive selector off a pane, so it can be answered from anywhere.

★ The owner's framing, which is the whole point of this module: *"we are forfeiting
interactive richness by not surfacing the interactive prompts, both in the shape of
those trust questions and when you format a series of tabbed questions for me to
answer on a plan, etc. We should be able to pipe that experience in and out."*

The prompts were never obstacles to route around. They are interaction that the
panel was flattening into text and then typing over the top of.

WHAT GOES WRONG WITHOUT THIS
An agent opens on a gate -- Claude asks whether the folder is trusted, Codex offers
to update itself -- and the pane is NOT at its input prompt. `send-keys` then types
the wearer's first message into that menu and the Enter selects the highlighted
option. Verified on real panes 2026-08-21: the first message vanished into Claude's
trust dialog, and on Codex the Enter picked "1. Update now", which shells out to
`npm install -g`. One cause, two bugs, and neither is fixable by waiting longer.

WHY SCRAPE RATHER THAN ASK
Nothing in the general case will tell us. Claude Code hooks can hand over the
structured form of ITS OWN questions (`AskUserQuestion`, `ExitPlanMode` are tools,
so a PreToolUse hook sees them as JSON), and that path is strictly better where it
applies. But trust gates, update banners, permission dialogs, npm and whatever ships
next month have no such channel. This is the universal fallback, and it stays a
fallback: when it cannot parse a selector it says so rather than guessing.

⚠️⚠️ THE FAILURE MODE TO FEAR IS SILENCE. A parser that recognises nothing looks
exactly like a pane with no prompt. The first version hard-coded Claude's cursor
glyph and Codex's menu was therefore invisible -- detected nothing, reported nothing,
and would have shipped that way. Hence `CURSORS` below, and hence the tests assert
against captures from BOTH tools.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

#: ⚠️ Cursor glyphs are per-tool and there is no standard: claude uses ❯, codex uses
#: › (U+203A). Anything that hard-codes one silently fails to see the other's menu.
CURSORS = "❯>▶›▸→•*◆●"

_OPTION_RE = re.compile(
    rf"^\s*(?P<cur>[{re.escape(CURSORS)}])?\s*(?P<n>\d{{1,2}})[\.\)]\s+(?P<text>\S.*?)\s*$"
)

#: Lines that mean "this is a thing awaiting a keypress", not just prose that happens
#: to contain a numbered list.
_FOOTER_RE = re.compile(
    r"(enter to confirm|esc to cancel|press enter|use arrow|arrow keys|↑/↓|to select)",
    re.I,
)

#: A rule/divider, which ends the question block above a menu.
_RULE_CHARS = set("─-=_━┄┈· ")

#: How many prose lines above the options may be taken as the question.
_MAX_QUESTION_LINES = 6

#: Options beyond this and it is almost certainly a numbered list in prose.
_MAX_OPTIONS = 12


@dataclass(frozen=True)
class Option:
    n: int
    text: str
    selected: bool = False

    def to_dict(self) -> dict:
        return {"n": self.n, "text": self.text, "selected": self.selected}


@dataclass(frozen=True)
class Prompt:
    question: str
    options: tuple[Option, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "options": [o.to_dict() for o in self.options],
        }

    @property
    def fingerprint(self) -> str:
        """Identity for dedupe.

        ⚠️ Deliberately EXCLUDES which option is selected. A menu repaints as the
        cursor moves; keying on the selection would emit a fresh prompt event every
        time an arrow key was pressed at the keyboard.
        """
        return " ".join([self.question, *(f"{o.n}:{o.text}" for o in self.options)])

    def summary(self) -> str:
        head = self.question or "waiting for an answer"
        return f"{head} ({len(self.options)} options)"


def _clean(line: str) -> str:
    """Drop the decorative symbols that would otherwise land in the question."""
    return "".join(
        ch for ch in line if unicodedata.category(ch) not in ("So", "Sk", "Cf")
    ).strip()


def _is_rule(text: str) -> bool:
    return bool(text) and set(text) <= _RULE_CHARS


def parse(screen: str) -> Prompt | None:
    """Return the selector the pane is showing, or None.

    Conservative on purpose: a false positive puts a fake question in front of the
    wearer and, worse, makes the hub queue his messages behind a prompt that does
    not exist. Prose containing "1. …  2. …" must NOT trip this, so a run of options
    only counts with a cursor glyph or an explicit footer to back it up.
    """
    if not screen:
        return None
    lines = [l.rstrip() for l in screen.splitlines()]

    options: list[Option] = []
    positions: list[int] = []
    for i, line in enumerate(lines):
        m = _OPTION_RE.match(line)
        if m:
            options.append(
                Option(int(m["n"]), _clean(m["text"]), bool(m["cur"]))
            )
            positions.append(i)

    if not 2 <= len(options) <= _MAX_OPTIONS:
        return None
    # must be 1..N in order: a real menu numbers itself, prose rarely does
    if [o.n for o in options] != list(range(1, len(options) + 1)):
        return None
    # ⚠️⚠️ NO CONTIGUITY RULE. It used to require the options on consecutive lines, to
    #    reject prose. It also rejected every REAL AskUserQuestion picker, because each
    #    option carries a wrapped description and a rule can sit between them:
    #
    #        ❯ 1. Spaces
    #             Indent with space characters (most common default...
    #          2. Tabs
    #          ...
    #        ────────────────────────────────
    #          4. Chat about this
    #
    #    That single rule is why he never saw a prompt: in two days the only thing it
    #    ever matched was the trust gate. Options may be spread, but must still be
    #    1..N in order and inside one screenful.
    if positions[-1] - positions[0] > 40:
        return None

    has_cursor = any(o.selected for o in options)
    has_footer = any(_FOOTER_RE.search(l) for l in lines)
    if not (has_cursor or has_footer):
        return None

    # ⚠️ A LIVE prompt is waiting for input, so it sits at the BOTTOM of the screen.
    #    Quoted menus scroll up and have output beneath them — that is how an agent
    #    *writing about* the trust dialog got announced as a real question, which would
    #    have queued his messages behind something nobody could answer.
    last_content = max(
        (i for i, l in enumerate(lines) if l.strip()), default=positions[-1]
    )
    #    Measured on the real captures: the trust gate and the AskUserQuestion picker
    #    both put their footer 1 line below the last option, codex 2. Three is margin,
    #    not a guess.
    if last_content - positions[-1] > 3:
        return None

    return Prompt(question=_question_above(lines, positions[0]),
                  options=tuple(options))


def _question_above(lines: list[str], first_option: int) -> str:
    """The prose block above the options, oldest first.

    ⚠️ NOT the nearest single line. On Claude's trust gate that line is the words
    "Security guide" -- a link label -- and using it made the surfaced question
    meaningless while looking like it worked.
    """
    picked: list[str] = []
    gap = 0
    for line in reversed(lines[:first_option]):
        text = _clean(line)
        if not text:
            gap += 1
            if gap >= 2 and picked:
                break
            continue
        if _is_rule(text) or _OPTION_RE.match(line):
            if picked:
                break
            continue
        gap = 0
        picked.append(text)
        if len(picked) >= _MAX_QUESTION_LINES:
            break
    return " ".join(reversed(picked))


def answer_keys(prompt: Prompt, option: int) -> list[str]:
    """The keystrokes that choose `option`.

    ★ The DIGIT, never a count of arrow presses. Arrow-counting needs the cursor's
    current position, which is read from a screen that may repaint between the read
    and the write; the digit is absolute and idempotent. Verified end to end on both
    Claude's trust gate and Codex's update menu.
    """
    if not any(o.n == option for o in prompt.options):
        raise ValueError(f"option {option} is not on this prompt")
    return [str(option), "Enter"]
