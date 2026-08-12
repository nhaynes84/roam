"""Record sources for the harness memory index -- the hub ledger and the
Claude session transcripts.

`~/.local/bin/memindex` indexes *markdown files*. The two corpora that matter
most for "what did we actually do" are not files: the hub's event ledger is a
SQLite table, and the sessions are JSONL. This module turns both into the same
chunk shape memindex already understands, so they become sources in the same
index, searchable with the same `memsearch` command.

★ It is deliberately not a ROAM feature. The ledger is one source; the sessions
are the bigger one, and they are useful from any session on this box.

⚠️ Nothing here writes to the index. It only produces chunks; memindex owns the
database, the embedding and the incremental logic.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Iterator

HUB_DIR = Path(__file__).resolve().parent
if str(HUB_DIR) not in sys.path:  # so `transcript` imports when run from memindex
    sys.path.insert(0, str(HUB_DIR))

from transcript import _assistant_groups, DEFAULT_TAIL_BYTES  # noqa: E402

LEDGER_DB = HUB_DIR / "hub.sqlite"
SESSION_DIR = Path.home() / ".claude/projects/-Users-talos"

#: Event kinds worth indexing. `opened`/`closed` are bookkeeping and `receipt`
#: duplicates the prompt that the session transcript already carries -- and an
#: echo receipt (`meta.echo_of`, see API.md) duplicates the `sent` in this very
#: table, so the sentence would be embedded twice out of one utterance.
LEDGER_KINDS = ("sent", "outcome", "error", "note", "notice")

#: Minimum characters before a chunk is worth indexing.
#:
#: Kept low on purpose: a short answer is still an answer ("391", "yes, ship
#: it"), and exact search is exactly where short literals matter. This only
#: filters the truly contentless.
MIN_CHUNK_CHARS = 12


# --------------------------------------------------------------- secrets

#: ⚠️ Decided before indexing, not after. Anything matching goes nowhere near
#: the index: an embedding is a copy, and a search result is a disclosure.
#:
#: These are shapes, not a promise. The real defence is that the *files* holding
#: secrets are excluded outright (`hub-token.txt`, `.venv`, dotfiles), and this
#: catches a credential someone pasted into a conversation.
_SECRET_PATTERNS = (
    re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_\-]{16,}"),        # API keys
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}"),              # GitHub tokens
    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"),           # Slack
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                      # AWS
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),        # private keys
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\."),  # JWTs
    re.compile(
        r"(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?token|"
        r"bearer)\b\s*[:=]\s*\S{8,}"
    ),
)

#: Files that must never be read by the indexer at all.
SECRET_FILENAMES = {"hub-token.txt", ".env", "credentials", "id_rsa", "id_ed25519"}


def looks_secret(text: str) -> bool:
    """Would indexing this text copy a credential into the search index?"""
    return any(pattern.search(text) for pattern in _SECRET_PATTERNS)


def redactable(text: str) -> str | None:
    """The text to index, or None if it must be skipped entirely."""
    if not text or len(text.strip()) < MIN_CHUNK_CHARS:
        return None
    if looks_secret(text):
        return None
    return text


# ---------------------------------------------------------------- ledger


def _stamp(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


def ledger_chunks(db_path: str | Path = LEDGER_DB) -> Iterator[dict[str, Any]]:
    """One chunk per meaningful hub event.

    Each carries its channel label and timestamp inline, because a result has
    to be usable read aloud: *which* channel, *when*, and what was said.

    ⚠️ Archived events -- and every event of an archived *channel* -- are
    excluded. Soft-delete has to reach the index too: "hidden from the thread
    but still findable in search" is not hidden, and the point of never
    hard-deleting is that recovery is deliberate, not that the data keeps
    surfacing on its own.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT e.id, e.pane_id, e.kind, e.body, e.summary, e.ts,
                   COALESCE(c.label, e.pane_id) AS label
            FROM events e
            LEFT JOIN channels c ON c.pane_id = e.pane_id
            WHERE e.kind IN ({placeholders})
              AND e.archived = 0
              AND COALESCE(c.archived, 0) = 0
            ORDER BY e.id
            """.format(placeholders=",".join("?" for _ in LEDGER_KINDS)),
            LEDGER_KINDS,
        ).fetchall()
    except sqlite3.Error:
        return
    finally:
        conn.close()

    for row in rows:
        body = (row["body"] or "").strip()
        text = redactable(f"{row['kind']} on {row['label']} ({_stamp(row['ts'])}):\n{body}")
        if text is None:
            continue
        yield {
            "id": f"ledger-{row['id']}",
            "path": f"ledger/{row['label']}",
            "text": text,
            "start_line": row["id"],
            "end_line": row["id"],
        }


# -------------------------------------------------------------- sessions


def _session_files(session_dir: Path) -> list[Path]:
    if not session_dir.is_dir():
        return []
    return sorted(p for p in session_dir.glob("*.jsonl") if p.is_file())


def _user_texts(record: dict[str, Any]) -> list[str]:
    message = record.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if isinstance(content, str):
        return [content]
    if not isinstance(content, list):
        return []
    out = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            out.append(block.get("text") or "")
    return out


def session_chunks(
    path: str | Path, tail_bytes: int = 0
) -> Iterator[dict[str, Any]]:
    """Turns of one Claude session: what was asked, and what was answered.

    Reuses `transcript._assistant_groups` -- the same parser the Stop hook uses,
    already tested against these files. There is exactly one implementation of
    this schema, and a second one is how the two drift apart.

    Tool calls and thinking blocks are excluded: thinking is not what was said,
    and tool JSON is noise that would swamp an index of prose.
    """
    path = Path(path)
    if path.name in SECRET_FILENAMES:
        return
    session = path.stem

    # Assistant turns, via the shared extractor.
    for index, (message_id, texts) in enumerate(
        _assistant_groups(path, tail_bytes or DEFAULT_TAIL_BYTES * 8)
    ):
        joined = "\n\n".join(t.strip() for t in texts if t.strip()).strip()
        text = redactable(joined)
        if text is None:
            continue
        yield {
            "id": f"session-{session}-a{index}",
            "path": f"sessions/{session}.jsonl",
            "text": f"claude ({session[:8]}):\n{text}",
            "start_line": index,
            "end_line": index,
        }

    # User prompts, straight from the file.
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for index, line in enumerate(raw.splitlines()):
        line = line.strip()
        if not line or '"type":"user"' not in line.replace(" ", ""):
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("type") != "user" or record.get("isSidechain"):
            continue
        joined = "\n\n".join(t.strip() for t in _user_texts(record) if t.strip())
        # Tool results arrive as user records; they are not things he said.
        if joined.startswith("<") or "tool_use_id" in line[:400]:
            continue
        text = redactable(joined)
        if text is None:
            continue
        yield {
            "id": f"session-{session}-u{index}",
            "path": f"sessions/{session}.jsonl",
            "text": f"nick ({session[:8]}):\n{text}",
            "start_line": index,
            "end_line": index,
        }


def session_sources(session_dir: str | Path = SESSION_DIR) -> Iterator[tuple[Path, float, int]]:
    """(path, mtime, size) for every session file -- the incremental key."""
    for path in _session_files(Path(session_dir)):
        try:
            stat = path.stat()
        except OSError:
            continue
        yield path, stat.st_mtime, stat.st_size


def all_session_chunks(session_dir: str | Path = SESSION_DIR) -> Iterator[dict[str, Any]]:
    for path, _mtime, _size in session_sources(session_dir):
        yield from session_chunks(path)
