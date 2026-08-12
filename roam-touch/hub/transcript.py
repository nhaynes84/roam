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


def last_assistant_text(
    path: str | Path, tail_bytes: int = DEFAULT_TAIL_BYTES
) -> str:
    """The text of the last assistant turn that actually said something.

    Returns "" when the transcript is missing, empty, or contains nothing but
    tool calls and thinking -- a hook must never explode over a missing file.
    """
    path = Path(path)
    if not path.exists():
        return ""
    try:
        records = list(_iter_records(path, tail_bytes))
    except TranscriptError:
        return ""

    # Group consecutive assistant records by message id; keep the last group
    # that yielded any text.
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

    for _, texts in reversed(groups):
        joined = "\n\n".join(t.strip() for t in texts if t.strip()).strip()
        if joined:
            return joined
    return ""


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
    out = _HEADING_RE.sub("", out)
    out = _QUOTE_RE.sub("", out)
    out = _BULLET_RE.sub("", out)
    out = _LINK_RE.sub(r"\1", out)
    out = _INLINE_CODE_RE.sub(r"\1", out)
    out = _EMPHASIS_RE.sub("", out)
    out = _strip_symbols(out)
    out = _WS_RE.sub(" ", out).strip()
    return _truncate(out, limit)


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
