"""tmux channel layer for the ROAM Touch hub.

A *channel* is one tmux pane running an agent. Channels are keyed on the tmux
**pane id** (`%3`), never on `session:window.pane` indices -- indices renumber
when panes close, so a saved channel would silently start pointing at a
different pane. For a device whose entire job is "send this to exactly that",
that is the worst available failure mode.

Pane ids are stable for the life of the pane and are never reused by tmux.
"""

from __future__ import annotations

import hashlib
import socket
import subprocess
from dataclasses import dataclass, asdict

#: tmux gives every pane the local hostname as its default title, so a bare
#: shell pane reports `pane_title = "talos"`. That is not a channel name -- it
#: would make every unnamed pane on the box look identically titled on the
#: panel. Treat it as "no title set".
_DEFAULT_TITLE = socket.gethostname().split(".")[0].lower()

# Tab-separated so titles containing spaces survive parsing.
_FMT = "\t".join(
    (
        "#{pane_id}",
        "#{session_name}",
        "#{window_index}",
        "#{pane_index}",
        "#{pane_current_command}",
        "#{pane_title}",
    )
)


class TmuxError(RuntimeError):
    """tmux is absent, not running a server, or rejected a command."""


@dataclass(frozen=True)
class Channel:
    pane_id: str          # "%3" -- the stable key
    session: str
    window: int
    index: int
    command: str
    title: str

    @property
    def label(self) -> str:
        """Human name for the panel.

        The pane title if the pane actually set one -- for a Claude pane that
        is the session summary, which is exactly what the wearer should see.
        A title equal to the session name or to the host's default title means
        nothing was set, so fall back to `session:window.pane`.
        """
        title = self.title.strip()
        if title and title != self.session and title.lower() != _DEFAULT_TITLE:
            return title
        return f"{self.session}:{self.window}.{self.index}"

    def to_dict(self) -> dict:
        return {**asdict(self), "label": self.label}


def _run(args: tuple[str, ...], stdin: str | None = None, check: bool = True) -> str:
    """The single place this module shells out. Tests patch exactly here."""
    try:
        proc = subprocess.run(
            ("tmux", *args),
            input=stdin,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except FileNotFoundError as exc:                      # tmux not installed
        raise TmuxError("tmux is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise TmuxError(f"tmux timed out: {' '.join(args)}") from exc
    if check and proc.returncode != 0:
        raise TmuxError(proc.stderr.strip() or f"tmux failed: {' '.join(args)}")
    return proc.stdout


def _tmux(*args: str, check: bool = True) -> str:
    return _run(args, check=check)


def list_channels() -> list[Channel]:
    """Every pane on this host, as channels. Empty list if no server running."""
    try:
        out = _tmux("list-panes", "-a", "-F", _FMT)
    except TmuxError as exc:
        if "no server running" in str(exc):
            return []
        raise
    channels = []
    for line in out.splitlines():
        if not line.strip():
            continue
        pane_id, session, window, index, command, *rest = line.split("\t")
        channels.append(
            Channel(
                pane_id=pane_id,
                session=session,
                window=int(window),
                index=int(index),
                command=command,
                title=rest[0] if rest else "",
            )
        )
    return channels


def get(pane_id: str) -> Channel | None:
    """The live channel for `pane_id`, or None if that pane is gone."""
    for c in list_channels():
        if c.pane_id == pane_id:
            return c
    return None


def exists(pane_id: str) -> bool:
    return get(pane_id) is not None


def send(pane_id: str, text: str, enter: bool = True) -> None:
    """Type `text` into a pane, optionally followed by Enter.

    Single-line text goes via `send-keys -l -- <text>` (literal) so the payload
    is never interpreted as key names -- without `-l` a transcript containing
    "Enter", "C-c" or "Escape" would be executed as keystrokes rather than
    typed. The `--` matters just as much: tmux parses a leading dash as an
    option, so `send-keys -l "-N thing"` fails with "repeat count invalid" and
    the message is silently lost (verified on tmux 3.7b, 2026-08-11).

    Multi-line text goes via a bracketed paste (`load-buffer` + `paste-buffer
    -p`), because typing a literal newline into a TUI submits the line: a
    three-line message sent with `send-keys -l` would fire as three separate
    prompts. Bracketed paste inserts the whole block as one value and lets the
    caller decide when to submit.

    Enter is always a separate, deliberate keystroke.
    """
    if not text:
        raise ValueError("refusing to send an empty message")
    if not exists(pane_id):
        raise TmuxError(f"no such pane: {pane_id}")
    if "\n" in text or "\r" in text:
        _paste(pane_id, text)
    else:
        _tmux("send-keys", "-t", pane_id, "-l", "--", text)
    if enter:
        _tmux("send-keys", "-t", pane_id, "Enter")


def press(pane_id: str, key: str) -> None:
    """Send one *named* key to a pane -- `Escape`, `C-c`.

    The deliberate opposite of `send()`: no `-l`, so tmux interprets the name
    as a key press. That is only ever safe for a fixed set of names chosen by
    the hub (see `hub.CONTROL_ACTIONS`); never pass user text through here, or
    "Enter C-c" in a transcript becomes two key presses.
    """
    if not key:
        raise ValueError("no key to press")
    if not exists(pane_id):
        raise TmuxError(f"no such pane: {pane_id}")
    _tmux("send-keys", "-t", pane_id, key)


def _paste(pane_id: str, text: str) -> None:
    """Load `text` into a private tmux buffer and paste it as one block."""
    buf = f"roam-{pane_id.lstrip('%')}"
    _run(("load-buffer", "-b", buf, "-"), stdin=text)
    # -p bracketed paste (the TUI sees one paste, not N keystrokes),
    # -d delete the buffer afterwards so transcripts don't pile up in tmux.
    _tmux("paste-buffer", "-p", "-d", "-b", buf, "-t", pane_id)


def screen_digest(pane_id: str) -> str:
    """A fingerprint of what is currently *visible* in a pane.

    The liveness signal. tmux 3.7b has no per-pane activity timestamp
    (`pane_activity` does not exist; `window_activity` is per *window*, so it
    reports pane A's output as pane B's), and hashing the visible screen is the
    honest substitute: an agent that is working repaints a spinner and an
    elapsed counter, so its screen changes; one that is wedged does not.

    Visible screen only -- no scrollback -- so this stays a few milliseconds.
    Returns "" if the pane is gone; callers treat that as "no reading".
    """
    try:
        content = _tmux("capture-pane", "-p", "-t", pane_id)
    except TmuxError:
        return ""
    return hashlib.sha1(content.encode("utf-8", "replace")).hexdigest()


def capture(pane_id: str, lines: int = 200) -> str:
    """Recent visible output of a pane, for read-back on the panel."""
    if not exists(pane_id):
        raise TmuxError(f"no such pane: {pane_id}")
    # -p print to stdout, -J join wrapped lines, -S negative = scrollback start
    return _tmux("capture-pane", "-p", "-J", "-t", pane_id, "-S", f"-{lines}")


def spawn(
    command: str = "claude",
    session: str | None = None,
    label: str | None = None,
    cwd: str | None = None,
) -> str:
    """Create a pane running `command` and return its pane id.

    A new window, never a split: splitting would carve up whatever the owner
    is looking at. `-d` keeps focus where it is, so a session created from the
    arm or the desk app never yanks the tmux client he is typing in. With no
    session given, the window lands in the first session that exists; with no
    server at all, a fresh "agents" session is started to hold it.
    """
    if session is None:
        existing = list_channels()
        session = existing[0].session if existing else None
    if session is not None:
        args = ["new-window", "-d", "-P", "-F", "#{pane_id}", "-t", f"{session}:"]
    else:
        args = ["new-session", "-d", "-P", "-F", "#{pane_id}", "-s", "agents"]
    if cwd:
        args += ["-c", cwd]
    args.append(command)
    pane_id = _tmux(*args).strip()
    if label:
        # The default pane title is the hostname, which reads as "talos" for
        # every unnamed pane -- name it while we know what it is for.
        _tmux("select-pane", "-t", pane_id, "-T", label)
    return pane_id


def kill(pane_id: str) -> None:
    """Kill the pane and whatever runs in it.

    The channel outlives the pane: history stays readable and the poller
    emits the canonical `closed` event when it sees the pane gone.
    """
    _tmux("kill-pane", "-t", pane_id)
