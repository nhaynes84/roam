"""Turning a Claude session transcript into something worth reading on a wrist.

An outcome that says "the response finished" is useless -- the whole point of
the device is not walking back to the computer to find out what was said. So
the `Stop` hook pulls the assistant's actual answer out of the session
transcript and that text is what lands in the channel.

The transcript is JSONL, one record per line, written by Claude Code. Verified
against the real files in `~/.claude/projects/-Users-talos/*.jsonl` on talos
(2026-08-11), not against a guessed schema:

* One assistant *turn* is spread over several records that share
  `message.id` -- typically a `thinking` record, then `text`, then `tool_use`.
  So "the last message" is a group of records, not the last record.
* `message.content` is a list of blocks; each record here carried exactly one,
  but the list form is real and a record may carry several.
* A turn can be `tool_use` only, or `thinking` only. Neither is an answer:
  walk back to the last turn that actually said something.
* `thinking` blocks are never included. They are not the answer, and reading
  them aloud would be worse than saying nothing.
* Sidechain records (`isSidechain: true`) belong to subagents, not to the
  session the hook fired for.

This module also holds the display/speech normalisation, because the same text
is spoken by Piper and glanced at on a 5" panel: `summarise()` for the short
form, `cap_body()` as the hard rail on what the store will hold.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Any, Iterator

#: Storage rail: 256 KiB of text per event. The full answer is always kept --
#: "summary first, expandable details" only works if the details still exist --
#: so this is not a display limit, it is the backstop against a pathological
#: reply (a dumped log, a runaway loop) bloating the database. Beyond it the
#: body is cut and `meta.truncated_from` records the original length.
MAX_BODY_CHARS = 262144

#: How much body travels inline in a *list* or stream response (history,
#: /events, WebSocket frames). The full text is always one fetch away at
#: `GET /events/{id}`, so this only bounds the size of a bulk payload on a
#: phone -- it never destroys anything.
INLINE_BODY_CHARS = 4096

#: The short form: one or two sentences. Long enough to be an answer, short
#: enough to read at a glance and to speak without a wait.
MAX_SUMMARY_CHARS = 280

#: How much of the tail of a transcript to read. Sessions grow to tens of MB;
#: the last answer is always at the end.
DEFAULT_TAIL_BYTES = 4 * 1024 * 1024

_CODE_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)(?:```|\Z)", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE)
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+", re.MULTILINE)
_QUOTE_RE = re.compile(r"^\s*>\s?", re.MULTILINE)
_EMPHASIS_RE = re.compile(r"(\*\*|\*|__|_|~~)")
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_HRULE_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$", re.MULTILINE)
_WS_RE = re.compile(r"\s+")


class TranscriptError(RuntimeError):
    """The transcript could not be read. Callers treat this as 'no text'."""


# ------------------------------------------------------------------ reading


def _iter_records(path: Path, tail_bytes: int) -> Iterator[dict[str, Any]]:
    """Yield parsed JSONL records from the tail of `path`.

    A partial first line (we may have landed mid-record) and any unparseable
    line are skipped rather than raising -- a half-written last line is normal
    when the hook fires while the file is still being appended to.
    """
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            if tail_bytes and size > tail_bytes:
                fh.seek(size - tail_bytes)
                fh.readline()  # discard the partial record
            raw = fh.read()
    except OSError as exc:
        raise TranscriptError(f"cannot read transcript: {exc}") from exc
    for line in raw.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            yield record


def _text_blocks(content: Any) -> list[str]:
    """The `text` blocks of one record's content, in order.

    `thinking` and `tool_use` are deliberately dropped. A bare string is the
    older content shape and is taken at face value.
    """
    if isinstance(content, str):
        return [content] if content.strip() else []
    if not isinstance(content, list):
        return []
    out = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "text":
            continue
        text = block.get("text") or ""
        if text.strip():
            out.append(text)
    return out


def _assistant_groups(
    path: Path, tail_bytes: int
) -> list[tuple[str, list[str]]]:
    """Assistant turns as (message_id, [text blocks]), oldest first."""
    if not path.exists() or path.is_dir():
        return []
    try:
        records = list(_iter_records(path, tail_bytes))
    except TranscriptError:
        return []
    groups: list[tuple[str, list[str]]] = []
    for record in records:
        if record.get("type") != "assistant" or record.get("isSidechain"):
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        message_id = str(message.get("id") or "")
        texts = _text_blocks(message.get("content"))
        if groups and groups[-1][0] == message_id and message_id:
            groups[-1][1].extend(texts)
        else:
            groups.append((message_id, list(texts)))
    return groups


def _newest_text(groups: list[tuple[str, list[str]]]) -> str:
    """The last group that said something, joined."""
    for _, texts in reversed(groups):
        joined = "\n\n".join(t.strip() for t in texts if t.strip()).strip()
        if joined:
            return joined
    return ""


def _ends_with_text(groups: list[tuple[str, list[str]]]) -> bool:
    """Is the *newest* turn a spoken one?

    This is the settle signal. When the newest assistant turn is `tool_use` or
    `thinking`, the turn's answer has not been flushed to disk yet -- walking
    back to an older text group at that moment returns the preamble, which is
    how a wrong-but-plausible answer once reached the user's arm.
    """
    if not groups:
        return False
    return any(t.strip() for t in groups[-1][1])


def last_assistant_text(
    path: str | Path, tail_bytes: int = DEFAULT_TAIL_BYTES
) -> str:
    """The text of the last assistant turn that actually said something.

    Returns "" when the transcript is missing, empty, or contains nothing but
    tool calls and thinking -- a hook must never explode over a missing file.
    """
    return _newest_text(_assistant_groups(Path(path), tail_bytes))


def settled_assistant_text(
    path: str | Path,
    timeout: float = 2.0,
    interval: float = 0.05,
    quiet_after: float = 0.4,
    tail_bytes: int = DEFAULT_TAIL_BYTES,
    sleep=None,
    clock=None,
) -> tuple[str, bool]:
    """The answer for *this* Stop, waiting briefly for it to hit the disk.

    Returns `(text, settled)`.

    The race, measured on a live session: the final assistant record carried a
    timestamp 143 ms *before* the hook's POST and still was not readable when
    the hook fired. Reading whatever is on disk at that instant returns real,
    plausible prose from the same turn -- the opening line before the tool
    calls -- with nothing to indicate it is the wrong block. That is worse than
    an empty body, which at least announces itself.

    So: if the newest turn on disk already spoke, take it and return
    immediately (the common case, no delay). Otherwise poll until it does, give
    up early once the file has gone quiet, and hard-stop at `timeout`.
    `settled=False` means the wait expired -- the caller must record that, so a
    wrong block is detectable rather than silent.

    ⚠️ This runs inside a hook. It is bounded on every path: a missed outcome
    is acceptable, a hung session is not.
    """
    # Resolved at call time, not bound as defaults, so a test (or a caller with
    # its own clock) can substitute them.
    sleep = sleep or time.sleep
    clock = clock or time.monotonic
    path = Path(path)
    deadline = clock() + max(0.0, timeout)
    groups = _assistant_groups(path, tail_bytes)
    if _ends_with_text(groups):
        return _newest_text(groups), True

    def signature() -> tuple[float, int]:
        try:
            stat = path.stat()
            return (stat.st_mtime, stat.st_size)
        except OSError:
            return (0.0, 0)

    last_signature = signature()
    last_change = clock()
    while clock() < deadline:
        sleep(interval)
        current = signature()
        if current != last_signature:
            last_signature = current
            last_change = clock()
            groups = _assistant_groups(path, tail_bytes)
            if _ends_with_text(groups):
                return _newest_text(groups), True
        elif quiet_after and clock() - last_change >= quiet_after:
            break  # nothing more is coming; don't burn the whole window
    return _newest_text(_assistant_groups(path, tail_bytes)), False


# ------------------------------------------------------- display and speech


def _fence_placeholder(match: re.Match[str]) -> str:
    lines = [ln for ln in match.group(1).splitlines() if ln.strip()]
    return f" [code, {len(lines)} line{'s' if len(lines) != 1 else ''}] "


def _strip_symbols(text: str) -> str:
    """Drop decorative symbols and emoji.

    Piper says nothing for them and they eat width on the panel. Punctuation,
    letters, digits and currency are untouched.

    Emoji drag invisible passengers -- variation selectors (U+FE0F) and zero
    width joiners -- which survive a category filter and leave a stray box on
    the panel, so they go too. Combining marks are left alone: they are how
    accented letters are spelled.
    """
    return "".join(
        ch
        for ch in text
        if unicodedata.category(ch) not in ("So", "Sk", "Cf")
        and not (0xFE00 <= ord(ch) <= 0xFE0F)
    )


def summarise(text: str, limit: int = MAX_SUMMARY_CHARS) -> str:
    """A one-glance, speakable version of an answer.

    Code blocks and tables become a note of what was there rather than being
    read out character by character; markdown scaffolding is removed; the
    result is cut at a sentence boundary near `limit`. The full text is always
    still on the event as `body` -- this never replaces it.
    """
    if not text:
        return ""
    out = _CODE_FENCE_RE.sub(_fence_placeholder, text)

    # Tables: collapse each block of pipe rows into one note.
    lines, table, kept = out.splitlines(), 0, []
    for line in lines:
        if _TABLE_ROW_RE.match(line):
            table += 1
            continue
        if table:
            kept.append(_table_note(table))
            table = 0
        kept.append(line)
    if table:
        kept.append(_table_note(table))
    out = "\n".join(kept)

    out = _HRULE_RE.sub(" ", out)
    # ⚠️ Headings and bullets must be TERMINATED, not just unmarked. Stripping "## "
    #    leaves the heading as a bare line, and _WS_RE then eats the newline — so
    #    "## The first message doesn't make it" welds onto the paragraph under it and
    #    reads as "...doesn't make it spawn() creates the tmux pane...". The owner
    #    caught exactly that on the panel. A structural line that does not already end
    #    in punctuation gets a full stop, which also gives Piper somewhere to breathe.
    lines, kept = out.splitlines(), []
    for line in lines:
        if _HEADING_RE.match(line):
            line = _terminate(_HEADING_RE.sub("", line))
        elif _BULLET_RE.match(line):
            line = _terminate(_BULLET_RE.sub("", line))
        kept.append(line)
    out = "\n".join(kept)
    out = _QUOTE_RE.sub("", out)
    out = _LINK_RE.sub(r"\1", out)
    out = _INLINE_CODE_RE.sub(r"\1", out)
    out = _EMPHASIS_RE.sub("", out)
    out = _strip_symbols(out)
    out = _WS_RE.sub(" ", out).strip()
    return _truncate(out, limit)


def _terminate(line: str) -> str:
    """End a structural line so it cannot weld onto the next one."""
    t = line.rstrip()
    if not t:
        return t
    return t if t[-1] in ".!?:;," else t + "."


def _table_note(rows: int) -> str:
    # The header and its separator are rows in the markdown but not data.
    body_rows = max(rows - 2, 0)
    if body_rows:
        return f" [table, {body_rows} row{'s' if body_rows != 1 else ''}] "
    return " [table] "


def _truncate(text: str, limit: int) -> str:
    """Cut at a sentence end if there is one nearby, else at a word."""
    if len(text) <= limit:
        return text
    window = text[: limit + 1]
    for stop in (". ", "! ", "? "):
        cut = window.rfind(stop)
        if cut >= limit * 0.6:
            return window[: cut + 1].strip()
    cut = window.rfind(" ")
    if cut <= 0:
        return window[:limit].rstrip() + "…"
    return window[:cut].rstrip() + "…"


def cap_body(text: str, limit: int = MAX_BODY_CHARS) -> tuple[str, int | None]:
    """Enforce the stored-size rail. Returns (body, original_length_if_cut)."""
    if not text or len(text) <= limit:
        return text or "", None
    marker = "\n… [truncated]"
    return text[: limit - len(marker)] + marker, len(text)
