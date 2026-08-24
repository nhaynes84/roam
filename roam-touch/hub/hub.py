"""ROAM Touch hub -- the always-on channel service on talos.

A *channel* is one tmux pane running an agent (see `channels.py`). The hub is
the thing that remembers what happened on each channel (see `store.py`) and
pushes new events to the arm-mounted client over a WebSocket, because an
outcome can land minutes after the prompt was sent -- when the wearer is
looking at another channel, or has the lid shut. The panel is a view; this is
the state.

Contract for clients: `API.md`, next to this file. Run: `README.md`.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import re
import secrets
import socket
import subprocess
import stat
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Iterator

from fastapi import (
    Depends,
    FastAPI,
    File,
    HTTPException,
    Path as PathParam,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import AliasChoices, BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.concurrency import run_in_threadpool

import channels as channels_mod
import files as files_mod
import images as images_mod
import intercom as intercom_mod
import prompts as prompts_mod
import radio as radio_mod
from channels import Channel, TmuxError
from presence import DEFAULT_TTL_S, UNKNOWN_COVERAGE, Presence
from store import (
    DEFAULT_DB_PATH,
    HOST_CHANNEL_ID,
    SCHEMA_VERSION,
    INPUT_APP,
    INPUT_TMUX,
    EventKind,
    Store,
    StoredChannel,
)
from transcript import INLINE_BODY_CHARS

HUB_DIR = Path(__file__).resolve().parent
#: HTML and the vendored three.js the file browser serves. See `web/browse.html`
#: for the browser constraints -- they are not negotiable and not obvious.
WEB_DIR = HUB_DIR / "web"
HUB_VERSION = "1.5.0"
PROTOCOL_VERSION = 1

#: WebSocket frames a subscriber may fall behind by before we cut it loose and
#: make it reconnect with `?since=` (which replays from the store, losslessly).
SUBSCRIBER_QUEUE_MAX = 512
#: Seconds of silence before the hub sends an application-level ping frame.
HEARTBEAT_SECONDS = 30.0

_PANE_RE = re.compile(r"^%\d+$")

#: Keystrokes the control endpoint may send, by name. An allow-list, not a
#: passthrough: `/interrupt` must never become "type arbitrary keys into a
#: shell". Values are tmux key names, sent as keys rather than literally.
CONTROL_ACTIONS: dict[str, str] = {
    "escape": "Escape",      # stop an agent mid-response
    "interrupt": "C-c",      # signal the foreground process
}

#: C0 control characters never belong in a typed message. Newline, carriage
#: return and tab do (multi-line paste), everything else is a key press and
#: belongs at `/interrupt` -- otherwise the ledger fills with raw bytes that
#: read as if the user typed them, and the search index inherits the noise.
_CONTROL_CHARS = {chr(c) for c in range(0x20)} - {"\n", "\r", "\t"}
_CONTROL_CHARS.add("\x7f")


#: The only files `/web/vendor/{name}` will serve. An allow-list, not a
#: directory: this must never become "read any path under web/".
VENDOR_ASSETS: frozenset[str] = frozenset(
    {"three.min.js", "STLLoader.js", "OrbitControls.js"}
)


def _js_literal(value: str) -> str:
    """A string as a safe JavaScript literal, for templating into a page.

    ⚠️ `json.dumps` alone is not enough inside a `<script>`: a value containing
    `</script>` ends the block early and everything after it is parsed as HTML,
    which is how a filename becomes script injection. A browse path arrives
    from a query string and a filename can legally contain a quote, so both go
    through here. (`ensure_ascii` already takes care of U+2028/U+2029, which
    are legal JSON but illegal inside a JS string literal.)
    """
    return (
        json.dumps(value, ensure_ascii=True)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def build_identity() -> dict[str, Any]:
    """What code is actually running.

    A stale launchd job served `coverage: null` for two commits while the test
    suite was green, and nothing in the API could tell a client that the
    process was older than the contract it was built against. Now it can ask.
    """
    commit = "unknown"
    try:
        proc = subprocess.run(
            ("git", "-C", str(HUB_DIR), "rev-parse", "--short", "HEAD"),
            capture_output=True,
            text=True,
            timeout=3,
        )
        if proc.returncode == 0:
            commit = proc.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        code_mtime = Path(__file__).stat().st_mtime
    except OSError:
        code_mtime = 0.0
    return {
        "version": HUB_VERSION,
        "protocol": PROTOCOL_VERSION,
        "commit": commit,
        "schema": SCHEMA_VERSION,
        "code_mtime": code_mtime,
    }

log = logging.getLogger("roam.hub")


# --------------------------------------------------------------------- config


class Settings(BaseSettings):
    """Hub configuration. Every field is settable as `ROAM_HUB_<FIELD>`."""

    model_config = SettingsConfigDict(env_prefix="ROAM_HUB_", extra="ignore")

    #: Bind address. Defaults to loopback so an accidental run is never
    #: exposed; the launchd job binds the Tailscale address explicitly.
    host: str = "127.0.0.1"
    port: int = 8787
    db_path: Path = DEFAULT_DB_PATH
    token_file: Path = HUB_DIR / "hub-token.txt"
    #: Overrides `token_file` when set (tests, one-off runs).
    token: str | None = None
    #: How often the hub re-reads the live pane list (seconds).
    poll_interval: float = 2.0
    #: Fingerprint each live pane's screen every poll, to answer "is it stuck?".
    #: One small capture-pane per pane per poll; off means `idle_s` stays null.
    activity_polling: bool = True
    capture_lines: int = 200
    history_limit: int = 200

    #: How long after the hub types a message into a pane the resulting hook
    #: receipt is still recognised as the echo of that send rather than as him
    #: typing at the keyboard.
    echo_window_s: float = 60.0

    #: The folders the file browser may see, and nothing else. Read-only: the
    #: hub never writes inside them (`POST /share` copies *out*, into the
    #: dropzone inbox).
    collab_cad: Path = files_mod.DEFAULT_ROOTS["CAD"]
    collab_photos: Path = files_mod.DEFAULT_ROOTS["Photos"]
    #: Where `POST /share` puts a file so Claude gets it. Same queue the photo
    #: bridge feeds -- see README.md, "the inbox contract".
    inbox: Path = files_mod.DEFAULT_INBOX
    #: Bytes for images posted into channels. Beside the DB, not in the repo.
    image_root: Path = DEFAULT_DB_PATH.parent / "images"
    thumb_cache: Path = files_mod.DEFAULT_THUMB_CACHE

    #: Where the station directory is cached. The browser never calls
    #: radio-browser.info itself -- see `radio.py` for why.
    radio_cache: Path = radio_mod.DEFAULT_CACHE_DIR

    log_level: str = "info"


def resolve_token(settings: Settings) -> str:
    """The shared bearer token, generating and persisting one on first run."""
    if settings.token:
        return settings.token
    path = Path(settings.token_file)
    if path.exists():
        token = path.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_urlsafe(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token + "\n", encoding="utf-8")
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0600
    log.warning("generated a new hub token at %s", path)
    return token


def normalise_pane_id(raw: str) -> str:
    """Accept `%3`, `3` or the percent-encoded `%253` and return `%3`.

    tmux pane ids start with `%`, which is the URL escape character -- an
    unencoded `%3` in a path is a malformed escape. Rather than make every
    client remember to encode it, the hub accepts the bare number too. Anything
    that is not a tmux pane id is rejected outright, so this can never widen
    into "send to whatever pane matches".

    ⚠️ One exception, and it is a literal rather than a pattern: `@host`, the
    channel that collects notices from things with no pane (`HOST_CHANNEL_ID`).
    It is not live and never can be, so `/send`, `/interrupt` and `/capture`
    answer 404 for it exactly as they do for a dead pane -- but its history and
    its channel entry have to be reachable, or the panel could list a thread it
    cannot open.
    """
    pane_id = raw.strip()
    if pane_id == HOST_CHANNEL_ID:
        return pane_id
    if pane_id and not pane_id.startswith("%"):
        pane_id = "%" + pane_id
    if not _PANE_RE.match(pane_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"not a tmux pane id: {raw!r} (expected '%3' or '3')",
        )
    return pane_id


# ---------------------------------------------------------------- pub/sub


class _Subscriber:
    """One WebSocket's outbound queue."""

    def __init__(self, maxsize: int = SUBSCRIBER_QUEUE_MAX) -> None:
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=maxsize)
        self.overflowed = False

    def offer(self, message: dict[str, Any]) -> None:
        if self.overflowed:
            return
        try:
            self.queue.put_nowait(message)
        except asyncio.QueueFull:
            # Dropping frames silently would desync the panel forever. Flag it;
            # the writer closes the socket and the client reconnects with
            # `?since=`, which replays from the store.
            self.overflowed = True


class Broadcaster:
    """Fan-out to every connected client. In-process; the store is the truth."""

    def __init__(self) -> None:
        self._subs: set[_Subscriber] = set()

    @contextlib.contextmanager
    def subscribe(self) -> Iterator[_Subscriber]:
        sub = _Subscriber()
        self._subs.add(sub)
        try:
            yield sub
        finally:
            self._subs.discard(sub)

    def publish(self, message: dict[str, Any]) -> None:
        for sub in list(self._subs):
            sub.offer(message)

    @property
    def subscriber_count(self) -> int:
        return len(self._subs)


# ------------------------------------------------------------------- models


class SendRequest(BaseModel):
    text: str = Field(min_length=1, description="Exactly what to type into the pane.")
    enter: bool = Field(
        default=True,
        description="Press Enter after the text. False stages it for review.",
    )
    origin: str = Field(
        default="client",
        description="Free-form tag for who sent it (client, cli, test...).",
    )


class EventRequest(BaseModel):
    """What the tmux/Claude hooks POST. `pane` is what `$TMUX_PANE` is called."""

    pane_id: str = Field(validation_alias=AliasChoices("pane_id", "pane"))
    kind: str = Field(
        description="sent | receipt | outcome | note | error (others allowed)"
    )
    body: str = ""
    meta: dict[str, Any] | None = None


class NoticeRequest(BaseModel):
    """"Tell the wearer this." What `roam-msg` posts.

    Deliberately *not* an `outcome`: an outcome is what an agent answered and
    belongs to the conversation. A notice is a tool talking about itself --
    "build finished", "I need input" -- and must not make a channel look like
    it owes a reply. It is still an event, so it is stored, stamped and
    searchable in the ledger like everything else.
    """

    text: str = Field(min_length=1, description="What to tell him.")
    pane: str | None = Field(
        default=None,
        description="The channel this is about -- `$TMUX_PANE`. Omit if there "
        "is none; it is then filed on the host channel.",
    )
    source: str = Field(
        default="cli", description="Who is speaking (roam-msg, a cron job...)."
    )
    meta: dict[str, Any] = Field(default_factory=dict)


class InterruptRequest(BaseModel):
    """Stop whatever the channel is doing. No text, so nothing is 'typed'."""

    action: str = Field(
        default="escape",
        description="escape (stop generating) | interrupt (C-c to the process)",
    )
    origin: str = Field(default="client", description="Who asked, for the log.")


class CreateChannelRequest(BaseModel):
    """POST /channels -- spawn a new agent pane."""

    command: str = Field(default="claude", min_length=1)
    label: str | None = None
    session: str | None = None
    cwd: str | None = None
    origin: str = "client"


class KillRequest(BaseModel):
    origin: str = "client"


class ArchiveRequest(BaseModel):
    archived: bool = True


class RespondRequest(BaseModel):
    """Choose one option on a pane's open selector."""

    option: int = Field(ge=1, le=12, description="The option number, as displayed.")


class ShareRequest(BaseModel):
    """Hand a browsed file to Claude.

    `path` is a browse path (`CAD/estack/drum_lh.step`), never a filesystem
    path -- see `files.resolve`. The file is *copied* into the dropzone inbox;
    nothing in the shared folders is ever moved or changed.
    """

    path: str = Field(min_length=1, max_length=1024)


class PresenceRequest(BaseModel):
    """What a client says about where the user is.

    The ROAM app foregrounded posts `{"source": "roam-app", "covers_all": true}`
    and re-posts while it stays up; backgrounding either DELETEs or simply lets
    the TTL lapse.
    """

    source: str = Field(min_length=1, description="Stable id for the reporter.")
    kind: str = Field(default="reported", description="app | client | reported…")
    panes: list[str] = Field(
        default_factory=list, description="Panes this source can already see."
    )
    covers_all: bool = Field(
        default=False, description="This source sees every channel (the panel)."
    )
    ttl_s: float = Field(
        default=DEFAULT_TTL_S, ge=1, le=3600, description="Believed for this long."
    )
    detail: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------- views


def channel_status(live: bool, last_kind: str | None) -> str:
    """`dead` | `working` | `idle` -- what the panel puts on the channel chip."""
    if not live:
        return "dead"
    if last_kind in (EventKind.SENT.value, EventKind.RECEIPT.value):
        return "working"
    return "idle"


#: What the panel calls the no-pane channel. The host name is the useful part:
#: "this came from talos, not from any session you started".
HOST_CHANNEL_LABEL = f"⌁ {socket.gethostname().split('.')[0]}"


def host_channel_view(store: Store, stored: StoredChannel | None) -> dict[str, Any]:
    """The `@host` channel -- notices from things that have no pane.

    It is not a pane, so `live` is neither true nor false in the usual sense.
    It is reported **live** because the alternative reads as `dead`, and a
    channel marked dead says "that session is gone" -- a lie about a box that
    is plainly running, and one that would push it to the bottom of the list.
    Nothing can be typed into it (`/send` still 404s: there is no pane), and it
    has no screen to fingerprint, so `idle_s` stays null rather than faking a
    zero.
    """
    last = store.last_event(HOST_CHANNEL_ID)
    return {
        "pane_id": HOST_CHANNEL_ID,
        "label": stored.label if stored and stored.label else HOST_CHANNEL_LABEL,
        "session": stored.session if stored else "",
        "window": None,
        "index": None,
        "command": None,
        "live": True,
        "status": "idle",  # it never owes an answer; nothing is sent to it
        "archived": bool(stored.archived) if stored else False,
        "first_seen": stored.first_seen if stored else None,
        "last_seen": stored.last_seen if stored else None,
        "last_output_at": None,
        "idle_s": None,
        "last_input_source": None,
        "last_input_at": None,
        "event_count": store.event_count(HOST_CHANNEL_ID),
        "last_event": last.to_dict(INLINE_BODY_CHARS) if last else None,
    }


def channel_view(
    store: Store,
    pane_id: str,
    live: Channel | None,
    stored: StoredChannel | None,
) -> dict[str, Any]:
    """One merged channel: whatever tmux says now, plus whatever we remember."""
    if pane_id == HOST_CHANNEL_ID:
        return host_channel_view(store, stored)
    last = store.last_event(pane_id)
    label = live.label if live else (stored.label if stored else pane_id)
    last_output_at = stored.last_output_at if stored else None
    idle_s = None
    if live is not None and last_output_at is not None:
        idle_s = round(max(0.0, time.time() - last_output_at), 1)
    return {
        "pane_id": pane_id,
        "label": label or pane_id,
        "session": live.session if live else (stored.session if stored else ""),
        "window": live.window if live else None,
        "index": live.index if live else None,
        "command": live.command if live else None,
        "live": live is not None,
        "status": channel_status(live is not None, last.kind if last else None),
        "archived": bool(stored.archived) if stored else False,
        "first_seen": stored.first_seen if stored else None,
        "last_seen": stored.last_seen if stored else None,
        # The heartbeat: when this pane's screen last changed, and how long ago.
        # `working` with idle_s climbing past a minute is the "is it stuck?"
        # answer that a bare status can never give.
        "last_output_at": last_output_at,
        "idle_s": idle_s,
        # Where this channel's conversation is happening, and therefore where
        # its next answer will be delivered.
        "last_input_source": stored.last_input_source if stored else None,
        "last_input_at": stored.last_input_at if stored else None,
        "event_count": store.event_count(pane_id),
        "last_event": last.to_dict(INLINE_BODY_CHARS) if last else None,
    }


def build_channel_list(
    store: Store,
    live_channels: list[Channel],
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    """Live panes merged with remembered ones.

    A channel whose pane has died keeps its history and stays in the list with
    `live: false` / `status: "dead"` -- the wearer must be able to read an
    outcome that arrived just before the session closed.
    """
    live_by_id = {c.pane_id: c for c in live_channels}
    stored_by_id = {s.pane_id: s for s in store.known_channels(include_archived=True)}
    views: list[dict[str, Any]] = []
    for pane_id in set(live_by_id) | set(stored_by_id):
        stored = stored_by_id.get(pane_id)
        if stored is not None and stored.archived and not include_archived:
            continue
        views.append(channel_view(store, pane_id, live_by_id.get(pane_id), stored))
    views.sort(
        key=lambda v: (
            0 if v["live"] else 1,
            -((v["last_event"] or {}).get("ts") or v["last_seen"] or 0.0),
            v["pane_id"],
        )
    )
    return views


# ----------------------------------------------------------------- the app


def create_app(settings: Settings | None = None, store: Store | None = None) -> FastAPI:
    settings = settings or Settings()
    token = resolve_token(settings)
    bearer = HTTPBearer(auto_error=False)

    async def require_auth(
        creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    ) -> None:
        supplied = creds.credentials if creds else ""
        if not supplied or not secrets.compare_digest(supplied, token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="bearer token required",
                headers={"WWW-Authenticate": "Bearer"},
            )

    async def require_auth_flex(
        creds: HTTPAuthorizationCredentials | None = Depends(bearer),
        token_q: str | None = Query(default=None, alias="token"),
    ) -> None:
        """Bearer header **or** `?token=`, for things a browser has to fetch.

        Exactly the concession `/ws` already makes, and for the same reason: a
        browser cannot put a header on `<img src>`, `<script src>` or a plain
        navigation, so a file browser that only accepted the header could not
        show a single thumbnail. The token then appears in the URL bar and in
        history, which is the cost -- mitigated by `Referrer-Policy:
        no-referrer` on the pages so it cannot leak to a third party, and by
        the hub being bound to the tailnet in the first place. Every endpoint
        that does not need it keeps `require_auth`.
        """
        supplied = creds.credentials if creds else (token_q or "")
        if not supplied or not secrets.compare_digest(supplied, token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="bearer token required",
                headers={"WWW-Authenticate": "Bearer"},
            )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.presence = Presence()
        app.state.store = store or Store(settings.db_path)
        app.state.broadcaster = Broadcaster()
        # Every event is stamped with the coverage in force when it happened.
        # Doing it here rather than at each call site means a new event kind
        # cannot quietly ship unstamped.
        app.state.store.coverage_provider = _coverage_for
        app.state.settings = settings
        app.state.token = token
        app.state.started_at = time.time()
        app.state.build = build_identity()
        app.state.tmux_ok = True
        app.state.live_channels = []
        #: pane_id -> the selector it is showing right now, or absent. Live state,
        #: so an answered question stops being answerable everywhere at once.
        app.state.prompts = {}
        #: pane_id -> messages held while that pane was asking a question.
        app.state.queued = {}
        #: The open audio channel and who currently holds the floor.
        app.state.intercom = intercom_mod.Intercom()
        app.state.intercom_peers = {}
        #: Video sockets, kept apart from audio so a frame cannot delay speech.
        app.state.video_peers = {}
        #: ⚠️ Diagnostic counters, per device: frames IN from it, frames OUT to it.
        #: Talk-back "does not come back across to the sender" is one of three very
        #: different faults — the receiver never captured, the hub never relayed, or
        #: the sender never played it. Guessing between them wasted a round trip; these
        #: split it in one test.
        app.state.intercom_stats = {}
        app.state.poller = asyncio.create_task(_poll_forever(app))
        try:
            yield
        finally:
            app.state.poller.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await app.state.poller
            if store is None:  # only close what we opened
                app.state.store.close()

    app = FastAPI(
        title="ROAM Touch hub",
        version=HUB_VERSION,
        summary="Channel state for the arm-mounted client. Contract: API.md",
        lifespan=lifespan,
    )

    # ------------------------------------------------------------ internals

    def _store() -> Store:
        return app.state.store

    def _publish(message: dict[str, Any]) -> None:
        app.state.broadcaster.publish(message)

    def _echo_key(text: str) -> str:
        """What two copies of the same message must agree on.

        ⚠️⚠️ NOT the whole body. It used to compare `body.strip() == typed`, and on a
        pasted TABLE the two never match. Diffed on the real pair (1683 chars sent,
        1764 reported, similarity 0.93): **every single difference is a TAB that came
        back as four spaces.**

            sent  '\tPurity\t'
            recpt '    Purity    '

        So the divergence is tab expansion by the agent's own input handling, not
        anything the hub does. Exact equality failed, the receipt was not recognised as
        an echo, and the thread drew his paste twice — "duped copy / paste in a chanel".

        ⚠️ Worth knowing separately: this means TAB-SENSITIVE content is altered in
        transit. Pasted tabular data is cosmetic, but a Makefile or a TSV sent through
        a channel arrives with its tabs expanded, and nothing warns about it.

        ★ Whitespace-normalised opening only. Tight enough to be safe — it is compared
        against the SINGLE most recent `sent` inside the echo window, not any message —
        and a false match is the dangerous direction, because a receipt marked as an
        echo stops being the record that he typed something.
        """
        return " ".join((text or "").split())[:200]

    def _note_prompt_origin(st: Store, pane_id: str, prompt: str) -> int | None:
        """A prompt was submitted in this pane. Was it him, or was it us?

        The `UserPromptSubmit` hook fires either way -- when he types at the
        keyboard *and* when the hub types the app's message into the pane. Left
        alone, the echo of an app message would flip the channel back to
        "he's at the keyboard" and silence the very answer he is waiting for on
        the phone.

        So: a receipt whose text matches the message we just sent is that echo,
        and changes nothing. Anything else is him typing.

        ★ Returns **the id of the `sent` it echoes**, or None when he typed it.
        That answer is the same question two other places were asking badly:
        the thread drew the sentence twice (`YOU`, then `PROMPT`) and the
        search index would have embedded it twice. Deciding it once, here, and
        stamping it on the event (`meta.echo_of`) means one thing he said is
        one entry everywhere -- and, crucially, a receipt with **no** mark is
        still the only record that a keyboard prompt happened, so it keeps
        rendering. Nothing suppresses receipts as a class.

        Edge case, accepted: typing the *same text by hand* within the echo
        window keeps the channel on `app` and produces one redundant
        notification. That is the harmless direction.
        """
        recent = st.history(pane_id, limit=6)
        typed = (prompt or "").strip()
        cutoff = time.time() - settings.echo_window_s
        for event in reversed(recent):
            if event.kind != EventKind.SENT.value or event.ts < cutoff:
                continue
            if not typed or _echo_key(event.body) == _echo_key(typed):
                # Our own send coming back: the conversation stays put, and the
                # event names the message it duplicates.
                return event.id
            break
        st.set_channel_input(pane_id, INPUT_TMUX)
        return None

    def _coverage_for(pane_id: str) -> dict[str, Any]:
        """Should an event on this channel reach his arm? Decided **now**, and
        frozen onto the event, because a backlog replayed tomorrow must be
        judged by where the conversation was when it happened.

        ★ **Reply where the last message came from.** He typed the prompt in
        tmux, so he is reading the answer in tmux -- covered, no buzz. He sent
        it from ROAM, so that is where the conversation is -- not covered, push.
        Switching is just sending from the other place. Nothing infers where he
        is; the message itself says.

        The one thing that rule cannot express is him *looking* at the panel
        without having sent anything, so a reported presence source
        (`POST /presence`) can also cover a channel. It only ever adds
        suppression, so the two can never disagree.

        ⚠️ No recorded source means **push**: a fresh pane, or an agent that
        spoke first. A missed message is worse than a redundant one.
        """
        stored = app.state.store.get_channel(pane_id)
        source = stored.last_input_source if stored else None
        reported = app.state.presence.covers(pane_id)
        if source is None and reported is None:
            return dict(UNKNOWN_COVERAGE)
        by: list[str] = []
        if source == INPUT_TMUX:
            by.append("tmux-input")
        if reported is not None:
            by.append(reported.id)
        return {"known": True, "covered": bool(by), "by": by, "last_input": source}

    def _publish_presence() -> None:
        _publish({"type": "presence", **app.state.presence.snapshot()})

    def _publish_event(event) -> None:
        # Stream frames carry the summary and a bounded body; the full text is
        # one fetch away at GET /events/{id}.
        _publish({"type": "event", "event": event.to_dict(INLINE_BODY_CHARS)})

    async def _live_channels() -> list[Channel]:
        try:
            live = await run_in_threadpool(channels_mod.list_channels)
        except TmuxError as exc:
            app.state.tmux_ok = False
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"tmux unavailable: {exc}",
            ) from exc
        app.state.tmux_ok = True
        app.state.live_channels = live
        return live

    # ------------------------------------------------------------ endpoints

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, Any]:
        """Liveness. Unauthenticated on purpose: launchd/monitoring use it."""
        return {
            "ok": True,
            "service": "roam-hub",
            "version": HUB_VERSION,
            "protocol": PROTOCOL_VERSION,
            "uptime_s": round(time.time() - app.state.started_at, 3),
            # So a client can tell whether the running process actually has the
            # code its contract describes. See `build_identity`.
            "build": app.state.build,
        }

    @app.get("/status", tags=["meta"], dependencies=[Depends(require_auth)])
    async def hub_status() -> dict[str, Any]:
        st = _store()
        return {
            "ok": True,
            "version": HUB_VERSION,
            "protocol": PROTOCOL_VERSION,
            "uptime_s": round(time.time() - app.state.started_at, 3),
            "tmux_ok": app.state.tmux_ok,
            "live_channels": len(app.state.live_channels),
            "known_channels": len(st.known_channels(include_archived=True)),
            "latest_event_id": st.latest_event_id(),
            # ⚠️ Nonzero means something told him about itself while this
            # process was not running, and nothing has adopted it yet. In
            # steady state it is 0 -- it is a fault signal, not a backlog.
            "pending_events": st.pending_count(),
            "subscribers": app.state.broadcaster.subscriber_count,
            "db_path": str(st.path),
            "build": app.state.build,
            "presence": app.state.presence.snapshot(),
        }

    # ------------------------------------------------------------ presence

    @app.get("/presence", tags=["presence"], dependencies=[Depends(require_auth)])
    async def get_presence() -> dict[str, Any]:
        """Where the user is, as far as the hub can tell."""
        return app.state.presence.snapshot()

    @app.post("/presence", tags=["presence"], dependencies=[Depends(require_auth)])
    async def post_presence(payload: PresenceRequest) -> dict[str, Any]:
        """Register or refresh a presence source.

        This is how the ROAM app says "I am foregrounded, stop notifying me" --
        first-class from the start, not a special case added later.
        """
        panes = [normalise_pane_id(p) for p in payload.panes]
        source = app.state.presence.report(
            payload.source,
            kind=payload.kind,
            panes=panes,
            covers_all=payload.covers_all,
            ttl_s=payload.ttl_s,
            detail=payload.detail,
        )
        _publish_presence()
        return {"source": source.to_dict(), "presence": app.state.presence.snapshot()}

    @app.delete(
        "/presence/{source}", tags=["presence"], dependencies=[Depends(require_auth)]
    )
    async def delete_presence(source: str = PathParam(...)) -> dict[str, Any]:
        """The app backgrounding, a device going away."""
        removed = app.state.presence.forget(source)
        if removed:
            _publish_presence()
        return {"removed": removed, "presence": app.state.presence.snapshot()}

    @app.get("/channels", tags=["channels"], dependencies=[Depends(require_auth)])
    async def list_channels_endpoint(
        include_archived: bool = Query(False),
    ) -> dict[str, Any]:
        live = await _live_channels()
        st = _store()
        await run_in_threadpool(_remember_all, st, live)
        return {
            "channels": build_channel_list(st, live, include_archived),
            "latest_event_id": st.latest_event_id(),
            "server_time": time.time(),
        }

    @app.get(
        "/channels/{pane}",
        tags=["channels"],
        dependencies=[Depends(require_auth)],
    )
    async def get_channel_endpoint(pane: str = PathParam(...)) -> dict[str, Any]:
        pane_id = normalise_pane_id(pane)
        st = _store()
        live = await _live_channels()
        stored = st.get_channel(pane_id)
        match = next((c for c in live if c.pane_id == pane_id), None)
        if match is None and stored is None:
            raise HTTPException(404, detail=f"unknown channel: {pane_id}")
        return {"channel": channel_view(st, pane_id, match, stored)}

    @app.post(
        "/channels",
        tags=["channels"],
        dependencies=[Depends(require_auth)],
        status_code=status.HTTP_201_CREATED,
    )
    async def create_channel_endpoint(payload: CreateChannelRequest | None = None):
        """Spawn a new agent pane; the new channel is live immediately.

        The pane is remembered before the poller can see it, so the `opened`
        event below is the only one -- the poller's first-time check finds the
        channel already known.
        """
        request = payload or CreateChannelRequest()
        try:
            pane_id = await run_in_threadpool(
                channels_mod.spawn,
                request.command,
                request.session,
                request.label,
                request.cwd,
            )
        except TmuxError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"tmux refused to create the pane: {exc}",
            ) from exc
        st = _store()
        live = await run_in_threadpool(channels_mod.get, pane_id)
        label = (live.label if live else None) or request.label or pane_id
        st.remember_channel(pane_id, label, live.session if live else request.session)
        event = st.append(
            pane_id,
            EventKind.OPENED,
            label,
            meta={"origin": request.origin, "spawned": True, "command": request.command},
        )
        _publish_event(event)
        all_live = await _live_channels()
        _publish(
            {
                "type": "channels",
                "channels": build_channel_list(st, all_live),
                "server_time": time.time(),
            }
        )
        return {"channel": channel_view(st, pane_id, live, st.get_channel(pane_id))}

    @app.post(
        "/channels/{pane}/kill",
        tags=["channels"],
        dependencies=[Depends(require_auth)],
    )
    async def kill_channel_endpoint(
        payload: KillRequest | None = None, pane: str = PathParam(...)
    ):
        """End the pane and whatever runs in it. History survives.

        Records a `control` event naming what was asked; the canonical
        `closed` comes from the poller when it sees the pane gone, exactly as
        for a pane that died any other way.
        """
        pane_id = normalise_pane_id(pane)
        request = payload or KillRequest()
        st = _store()
        live = await run_in_threadpool(channels_mod.get, pane_id)
        if live is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"channel {pane_id} is not live; nothing to kill",
            )
        try:
            await run_in_threadpool(channels_mod.kill, pane_id)
        except TmuxError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"tmux refused the kill: {exc}",
            ) from exc
        event = st.append(
            pane_id,
            EventKind.CONTROL,
            "kill",
            meta={"key": "kill-pane", "origin": request.origin},
        )
        _publish_event(event)
        return {
            "event": event.to_dict(),
            "channel": channel_view(st, pane_id, None, st.get_channel(pane_id)),
        }

    @app.post(
        "/channels/{pane}/respond",
        tags=["channels"],
        dependencies=[Depends(require_auth)],
    )
    async def respond_endpoint(payload: RespondRequest, pane: str = PathParam(...)):
        """Answer the selector a pane is showing.

        ★ Answered by DIGIT, never by counting arrow presses: the cursor's position
        is read off a screen that can repaint between the read and the write, while
        the digit is absolute and idempotent.
        ⚠️ Validated against the LIVE prompt, so a stale client cannot answer a
        question that has already gone -- which would otherwise type a bare number
        into a working agent.
        """
        pane_id = normalise_pane_id(pane)
        st = _store()
        current = app.state.prompts.get(pane_id)
        if current is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"channel {pane_id} is not asking anything right now",
            )
        prompt = prompts_mod.Prompt(
            question=current["question"],
            options=tuple(
                prompts_mod.Option(o["n"], o["text"], o.get("selected", False))
                for o in current["options"]
            ),
        )
        try:
            keys = prompts_mod.answer_keys(prompt, payload.option)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc

        chosen = next(o for o in prompt.options if o.n == payload.option)
        try:
            for key in keys:
                await run_in_threadpool(channels_mod.press, pane_id, key)
        except (TmuxError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=str(exc)
            ) from exc

        # It is answered: stop offering it everywhere, at once.
        app.state.prompts.pop(pane_id, None)
        event = st.append(
            pane_id,
            EventKind.SENT,
            f"answered: {chosen.text}",
            meta={"answered": prompt.to_dict(), "option": payload.option},
        )
        app.state.broadcaster.publish({"type": "event", "event": event.to_dict()})
        app.state.broadcaster.publish(
            {"type": "prompt", "pane": pane_id, "prompt": None}
        )

        # ★ Whatever he typed while the question was up goes now -- but NOT inline.
        #   Flushing here reported success and lost the message: the gate had only
        #   just cleared and the TUI was still painting. The flush waits for the pane
        #   to settle, which takes seconds, so it runs as a task and the answer
        #   returns immediately.
        held = app.state.queued.get(pane_id, [])
        if held:
            asyncio.create_task(_flush_when_ready(app, pane_id))
        return {
            "answered": chosen.text,
            "option": payload.option,
            "flushing": len(held),
        }

    @app.post(
        "/channels/{pane}/send",
        tags=["channels"],
        dependencies=[Depends(require_auth)],
    )
    async def send_endpoint(payload: SendRequest, pane: str = PathParam(...)):
        pane_id = normalise_pane_id(pane)
        st = _store()
        offending = sorted(_CONTROL_CHARS & set(payload.text))
        if offending:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "control characters cannot be typed as a message "
                    f"({[hex(ord(c)) for c in offending]}); "
                    "use POST /channels/{pane}/interrupt"
                ),
            )
        live = await run_in_threadpool(channels_mod.get, pane_id)
        if live is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"channel {pane_id} is not live; nothing was sent",
            )
        # ★★ HOLD, do not type. The pane is showing a selector, so `send-keys` would
        #    type his words INTO the menu and the Enter would pick whatever is
        #    highlighted -- which is exactly the bug that ate his first message and
        #    the one that told Codex to run `npm install -g`. His call between
        #    queueing and blocking the composer: "queue is friendlier and never loses
        #    your words". Flushed by /respond once the question is answered.
        if pane_id in app.state.prompts:
            app.state.queued.setdefault(pane_id, []).append(payload.text)
            return {
                "queued": True,
                "pane": pane_id,
                "waiting_on": app.state.prompts[pane_id],
                "detail": "held until the open prompt is answered",
            }
        try:
            await run_in_threadpool(
                channels_mod.send, pane_id, payload.text, payload.enter
            )
        except (TmuxError, ValueError) as exc:
            event = st.append(
                pane_id,
                EventKind.ERROR,
                str(exc),
                meta={"attempted": payload.text, "origin": payload.origin},
            )
            _publish_event(event)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"tmux refused the send: {exc}",
            ) from exc
        # The conversation moved here: he sent this from the app, so the answer
        # belongs on the app. Recorded before the event, so the event's own
        # stamp already reflects the switch.
        st.remember_channel(pane_id, live.label, live.session)
        st.set_channel_input(pane_id, INPUT_APP)
        event = st.append(
            pane_id,
            EventKind.SENT,
            payload.text,
            meta={"origin": payload.origin, "enter": payload.enter},
        )
        _publish_event(event)
        return {
            "event": event.to_dict(),
            "channel": channel_view(st, pane_id, live, st.get_channel(pane_id)),
        }

    @app.post(
        "/channels/{pane}/interrupt",
        tags=["channels"],
        dependencies=[Depends(require_auth)],
    )
    async def interrupt_endpoint(
        payload: InterruptRequest | None = None, pane: str = PathParam(...)
    ):
        """Send a control key without pretending the user typed one.

        Firing Escape through `/send` works -- it types literally -- but it
        stores a `sent` event whose body is a raw control byte, which reads in
        the thread as if he sent it and lands in the search index as noise.
        This records what actually happened instead: a `control` event naming
        the action.
        """
        pane_id = normalise_pane_id(pane)
        request = payload or InterruptRequest()
        key = CONTROL_ACTIONS.get(request.action)
        if key is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"unknown action {request.action!r}; "
                    f"expected one of {sorted(CONTROL_ACTIONS)}"
                ),
            )
        st = _store()
        live = await run_in_threadpool(channels_mod.get, pane_id)
        if live is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"channel {pane_id} is not live; nothing was sent",
            )
        try:
            await run_in_threadpool(channels_mod.press, pane_id, key)
        except (TmuxError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"tmux refused the key: {exc}",
            ) from exc
        event = st.append(
            pane_id,
            EventKind.CONTROL,
            request.action,
            meta={"key": key, "origin": request.origin},
        )
        _publish_event(event)
        return {
            "event": event.to_dict(),
            "channel": channel_view(st, pane_id, live, st.get_channel(pane_id)),
        }

    @app.get(
        "/channels/{pane}/history",
        tags=["channels"],
        dependencies=[Depends(require_auth)],
    )
    async def history_endpoint(
        pane: str = PathParam(...),
        limit: int = Query(default=None, ge=1, le=2000),
        since: int | None = Query(default=None, ge=0),
        include_archived: bool = Query(False),
    ) -> dict[str, Any]:
        pane_id = normalise_pane_id(pane)
        st = _store()
        events = st.history(
            pane_id,
            limit=limit or settings.history_limit,
            since=since,
            include_archived=include_archived,
        )
        return {
            "pane_id": pane_id,
            "events": [e.to_dict(INLINE_BODY_CHARS) for e in events],
            "latest_event_id": st.latest_event_id(),
        }

    @app.delete(
        "/channels/{pane}/history",
        tags=["channels"],
        dependencies=[Depends(require_auth)],
    )
    async def clear_history_endpoint(pane: str = PathParam(...)) -> dict[str, Any]:
        """Soft-clear: rows are flagged archived, never deleted."""
        pane_id = normalise_pane_id(pane)
        st = _store()
        archived = st.archive_history(pane_id)
        _publish({"type": "history_cleared", "pane_id": pane_id, "archived": archived})
        return {"pane_id": pane_id, "archived": archived, "deleted": 0}

    @app.post(
        "/channels/{pane}/archive",
        tags=["channels"],
        dependencies=[Depends(require_auth)],
    )
    async def archive_channel_endpoint(
        payload: ArchiveRequest | None = None, pane: str = PathParam(...)
    ) -> dict[str, Any]:
        """Hide (or unhide) a channel. History is kept either way."""
        pane_id = normalise_pane_id(pane)
        archived = True if payload is None else payload.archived
        st = _store()
        if st.get_channel(pane_id) is None:
            raise HTTPException(404, detail=f"unknown channel: {pane_id}")
        st.set_channel_archived(pane_id, archived)
        stored = st.get_channel(pane_id)
        live = await run_in_threadpool(channels_mod.get, pane_id)
        view = channel_view(st, pane_id, live, stored)
        _publish({"type": "channel", "channel": view})
        return {"channel": view}

    @app.get(
        "/channels/{pane}/capture",
        tags=["channels"],
        dependencies=[Depends(require_auth)],
    )
    async def capture_endpoint(
        pane: str = PathParam(...),
        lines: int = Query(default=None, ge=1, le=5000),
    ) -> dict[str, Any]:
        pane_id = normalise_pane_id(pane)
        want = lines or settings.capture_lines
        try:
            text = await run_in_threadpool(channels_mod.capture, pane_id, want)
        except TmuxError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"cannot capture {pane_id}: {exc}",
            ) from exc
        return {"pane_id": pane_id, "lines": want, "text": text}

    @app.post(
        "/events",
        tags=["events"],
        dependencies=[Depends(require_auth)],
        status_code=status.HTTP_201_CREATED,
    )
    async def post_event(payload: EventRequest) -> dict[str, Any]:
        """Where the tmux/Claude hooks POST receipts and outcomes.

        The pane is whatever `$TMUX_PANE` held when the hook fired, so a
        receipt lands on exactly the channel that was prompted.
        """
        pane_id = normalise_pane_id(payload.pane_id)
        st = _store()
        if st.get_channel(pane_id) is None:
            live = await run_in_threadpool(channels_mod.get, pane_id)
            st.remember_channel(
                pane_id,
                live.label if live else pane_id,
                live.session if live else "",
            )
        meta = payload.meta
        if payload.kind == EventKind.RECEIPT.value:
            echo_of = _note_prompt_origin(st, pane_id, payload.body)
            if echo_of is not None:
                meta = {**(meta or {}), "echo_of": echo_of}
        event = st.append(pane_id, payload.kind, payload.body, meta)
        _publish_event(event)
        return {"event": event.to_dict()}

    @app.post(
        "/notify",
        tags=["events"],
        dependencies=[Depends(require_auth)],
        status_code=status.HTTP_201_CREATED,
    )
    async def notify(payload: NoticeRequest) -> dict[str, Any]:
        """★ "Tell the wearer this" -- the one way a tool reaches his arm.

        `~/CLAUDE.md` tells every agent on this box to push its status to ROAM,
        and `roam-msg` used to do that by shelling out to `adb` on the phone.
        So the hub owned the notification policy for outcomes and for nothing
        else, and the device rang all day two feet from his hands. **Every
        route to the phone now ends here**, and the bridge is the only thing
        that touches the device.

        What that buys: one policy, in one place, applied to a status line
        exactly as it is applied to the answer that status line is about. He
        typed the prompt in that pane, so he is watching it -- the agent's
        chatter about it stays quiet, and the same message on a channel he is
        talking to from ROAM comes through.

        It answers with the decision (`push`, and why) rather than making the
        caller ask a second question. Delivery itself is the bridge's, so a
        `push: true` means "queued for the phone", not "it buzzed".
        """
        st = _store()
        live = None
        if payload.pane is None:
            pane_id = HOST_CHANNEL_ID
        else:
            pane_id = normalise_pane_id(payload.pane)
        created = st.get_channel(pane_id) is None
        if created:
            if pane_id == HOST_CHANNEL_ID:
                st.remember_channel(pane_id, HOST_CHANNEL_LABEL, socket.gethostname())
            else:
                live = await run_in_threadpool(channels_mod.get, pane_id)
                st.remember_channel(
                    pane_id,
                    live.label if live else pane_id,
                    live.session if live else "",
                )
            # Announce it before the event that made it exist. A subscriber
            # that has never heard of this channel would otherwise label the
            # notification with a raw id until the next poll -- and the first
            # notification from a new channel is exactly the one that has to
            # say who is speaking.
            _publish(
                {
                    "type": "channel",
                    "channel": channel_view(st, pane_id, live, st.get_channel(pane_id)),
                }
            )
        meta = {**payload.meta, "source": payload.source}
        event = st.append(pane_id, EventKind.NOTICE, payload.text, meta)
        _publish_event(event)
        coverage = event.coverage or {}
        covered = bool(coverage.get("covered"))
        if covered:
            reason = "covered by " + (", ".join(coverage.get("by") or []) or "presence")
        elif coverage.get("known"):
            reason = f"not covered (last input: {coverage.get('last_input')})"
        else:
            reason = "nothing recorded -- unknown means push"
        return {
            "event": event.to_dict(),
            "push": not covered,
            "reason": reason,
            # What is still sitting in the ledger unadopted. Almost always 0;
            # a successful call is the moment the caller is most able to say
            # "an earlier message went around the hub" out loud.
            "pending": st.pending_count(),
        }

    @app.get("/events", tags=["events"], dependencies=[Depends(require_auth)])
    async def get_events(
        since: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=2000)
    ) -> dict[str, Any]:
        """Everything after `since`, across all channels -- WebSocket catch-up
        for clients that would rather poll once on wake than hold a socket."""
        st = _store()
        events = st.events_since(since, limit)
        return {
            "events": [e.to_dict(INLINE_BODY_CHARS) for e in events],
            "latest_event_id": st.latest_event_id(),
        }

    @app.get(
        "/events/{event_id}", tags=["events"], dependencies=[Depends(require_auth)]
    )
    async def get_event(event_id: int = PathParam(..., ge=1)) -> dict[str, Any]:
        """One event, whole. This is "expand the details".

        Summaries and list payloads are bounded; this never is. Nothing the
        client shows is ever the only copy of the answer.
        """
        event = _store().get_event(event_id)
        if event is None:
            raise HTTPException(404, detail=f"no such event: {event_id}")
        return {"event": event.to_dict()}

    # --------------------------------------------------------------- files
    #
    # A read-only window onto ~/Collab/CAD and ~/Collab/Photos, so a part can be
    # looked at from the arm instead of from the desk, and handed to Claude with
    # one tap. All the path safety lives in `files.py`; these routes only map
    # its two exception types onto status codes.

    roots = {"CAD": settings.collab_cad, "Photos": settings.collab_photos}

    def _browse_error(exc: files_mod.BrowseError) -> HTTPException:
        # 404 for "not there", 400 for "not yours". Never echo a filesystem
        # path back -- the message is `files.py`'s, which is written to be safe
        # to show, and confirming where the roots live is free information.
        if isinstance(exc, files_mod.NotFound):
            return HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))
        return HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))

    def _page(name: str, replacements: dict[str, str]) -> HTMLResponse:
        """Serve one of the `web/` pages with its placeholders filled in.

        ⚠️ Substituted values land inside a JS string literal, so they go
        through `_js_literal` -- a filename may legally contain a quote, and
        the model path arrives from a query string. `no-referrer` stops the
        `?token=` in the URL from being handed to anything the page links to.
        """
        html = (WEB_DIR / name).read_text(encoding="utf-8")
        for placeholder, value in replacements.items():
            html = html.replace(placeholder, value)
        return HTMLResponse(
            html,
            headers={
                "Referrer-Policy": "no-referrer",
                "Cache-Control": "no-store",
            },
        )

    @app.get("/files", tags=["files"], dependencies=[Depends(require_auth_flex)])
    async def list_files(path: str = Query("", max_length=1024)) -> dict[str, Any]:
        """One directory. An empty `path` lists the roots themselves."""
        try:
            return await run_in_threadpool(files_mod.listdir, path, roots)
        except files_mod.BrowseError as exc:
            raise _browse_error(exc) from exc

    @app.get(
        "/files/raw", tags=["files"], dependencies=[Depends(require_auth_flex)]
    )
    async def raw_file(path: str = Query(..., max_length=1024)) -> FileResponse:
        """The file itself -- the `<img>` target, the STL the viewer loads."""
        try:
            target = await run_in_threadpool(files_mod.resolve_file, path, roots)
        except files_mod.BrowseError as exc:
            raise _browse_error(exc) from exc
        return FileResponse(
            target,
            filename=target.name,
            content_disposition_type="inline",
            headers={"Referrer-Policy": "no-referrer"},
        )

    @app.get(
        "/files/thumb", tags=["files"], dependencies=[Depends(require_auth_flex)]
    )
    async def thumb_file(
        path: str = Query(..., max_length=1024),
        size: int = Query(320, ge=48, le=1024),
    ) -> FileResponse:
        """A small JPEG for the grid, falling back to the original.

        A 2 MB phone photo per tile is a real cost over a tailnet link to a
        Pixel 1, so this shells out to `sips` and caches. If that is not
        available the page still works -- it is just heavier.
        """
        try:
            target = await run_in_threadpool(files_mod.resolve_file, path, roots)
        except files_mod.BrowseError as exc:
            raise _browse_error(exc) from exc
        small = await run_in_threadpool(
            files_mod.thumbnail, target, size, settings.thumb_cache
        )
        return FileResponse(
            small or target,
            content_disposition_type="inline",
            headers={"Referrer-Policy": "no-referrer"},
        )

    @app.post("/upload", tags=["files"], dependencies=[Depends(require_auth_flex)])
    async def upload_file(file: UploadFile = File(...)) -> dict[str, Any]:
        """Hand Claude a file that is NOT on talos -- an attachment from a client.

        ★ `/share` can only pass along something already sitting in the shared
        folders. This is the same inbox door opened from the other side, so a photo
        or a STEP on the laptop can reach Claude without going via Google Photos or
        a screenshot. Same honest promise as /share: "shared" means "will be in
        front of Claude on his next prompt", not "is on disk somewhere".
        """
        data = await file.read()
        try:
            landed = await run_in_threadpool(
                files_mod.deposit, file.filename or "attachment", data, settings.inbox
            )
        except files_mod.BrowseError as exc:
            raise _browse_error(exc) from exc
        except OSError as exc:
            raise HTTPException(
                status.HTTP_507_INSUFFICIENT_STORAGE, detail=f"could not write: {exc}"
            ) from exc
        return {"shared": landed.name, "bytes": len(data)}

    @app.post("/share", tags=["files"], dependencies=[Depends(require_auth_flex)])
    async def share_file(payload: ShareRequest) -> dict[str, Any]:
        """Copy a browsed file into `~/.claude/dropzone/inbox/`.

        ★ The same door the shared-album photos come through. Claude does not
        watch the filesystem; the `UserPromptSubmit` hook moves the inbox into
        the dropzone and *names* each file, and that naming is what makes it
        visible. So "shared" here means "will be in front of Claude on his next
        prompt", not "is on disk somewhere" -- which is the honest thing for
        the button to promise.
        """
        try:
            landed = await run_in_threadpool(
                files_mod.share, payload.path, roots, settings.inbox
            )
        except files_mod.BrowseError as exc:
            raise _browse_error(exc) from exc
        except OSError as exc:
            raise HTTPException(
                status.HTTP_507_INSUFFICIENT_STORAGE, detail=f"could not copy: {exc}"
            ) from exc
        log.info("shared %s -> %s", payload.path, landed)
        return {
            "ok": True,
            "path": payload.path,
            "name": landed.name,
            "inbox": str(landed),
            "note": "reaches Claude on the next prompt, via the dropzone hook",
        }

    @app.get(
        "/browse",
        tags=["files"],
        dependencies=[Depends(require_auth_flex)],
        response_class=HTMLResponse,
    )
    async def browse_page() -> HTMLResponse:
        """The file browser, for a phone browser. See `web/browse.html`."""
        return _page("browse.html", {'"__ROAM_TOKEN__"': _js_literal(token)})

    @app.get(
        "/view/stl",
        tags=["files"],
        dependencies=[Depends(require_auth_flex)],
        response_class=HTMLResponse,
    )
    async def stl_page(path: str = Query(..., max_length=1024)) -> HTMLResponse:
        """The STL viewer. ⚠️ **STL only** -- see `web/stl.html` for why.

        The path is resolved before the page is served, so a bad one is a 404
        here rather than a viewer that loads, spins and fails.
        """
        try:
            target = await run_in_threadpool(files_mod.resolve_file, path, roots)
        except files_mod.BrowseError as exc:
            raise _browse_error(exc) from exc
        if files_mod.classify(target) != "mesh":
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"only STL can be rendered, not {target.suffix or 'that'}",
            )
        return _page(
            "stl.html",
            {
                '"__ROAM_TOKEN__"': _js_literal(token),
                '"__MODEL_PATH__"': _js_literal(path),
                "__VENDOR__": "/web/vendor",
            },
        )

    @app.get("/web/vendor/{name}", tags=["files"], include_in_schema=False)
    async def vendor_asset(name: str = PathParam(...)) -> FileResponse:
        """The vendored three.js. Unauthenticated **on purpose**.

        It is public MIT library code with nothing of his in it, and the
        alternative -- a `?token=` on every `<script src>` -- would scatter the
        token through more URLs to protect a file anyone can download from
        unpkg. An explicit allow-list, so this can never become "serve any file
        under web/".
        """
        if name not in VENDOR_ASSETS:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no such asset")
        return FileResponse(
            WEB_DIR / "vendor" / name,
            media_type="application/javascript",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    # --------------------------------------------------------------- radio
    # He has no music on the device and no account on it. `GET /radio` is a
    # station list and a bare `<audio>` tag; `radio.py` is the part that knows
    # which streams a 2019 engine can actually decode.

    @app.get(
        "/radio/stations", tags=["radio"], dependencies=[Depends(require_auth_flex)]
    )
    async def radio_stations(
        q: str = Query("", max_length=radio_mod.MAX_QUERY_CHARS),
    ) -> dict[str, Any]:
        """The curated list, or a search. Never the browser's own API call.

        `source` says where the answer came from -- `live`, `cache`, `stale`
        (the directory was unreachable, this is the last good answer) or
        `builtin` (the baked-in favourites). The page shows the last two as
        such rather than presenting a possibly-rotted list as current.
        """
        try:
            return await run_in_threadpool(
                radio_mod.stations, q, settings.radio_cache
            )
        except radio_mod.RadioUnavailable as exc:
            # 502: the hub is fine, the thing behind it is not. A 500 would
            # send the client looking for a bug on this side.
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        except radio_mod.RadioError as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc

    @app.get(
        "/radio",
        tags=["radio"],
        dependencies=[Depends(require_auth_flex)],
        response_class=HTMLResponse,
    )
    async def radio_page() -> HTMLResponse:
        """The radio, for a phone browser. See `web/radio.html`."""
        return _page("radio.html", {'"__ROAM_TOKEN__"': _js_literal(token)})

    # ----------------------------------------------------------- websocket

    @app.post(
        "/channels/{pane}/image",
        tags=["channels"],
        dependencies=[Depends(require_auth_flex)],
    )
    async def post_image(
        pane: str = PathParam(...),
        file: UploadFile = File(...),
        caption: str = Query(default=""),
    ) -> dict[str, Any]:
        """Put an image IN the conversation.

        ★ "you should be able to dump images into these channel feeds, that is the
        direction you should go, don't point me elsewhere." Before this the only way to
        show him a picture was to file it in a shared folder and describe where to look.
        This makes it an ordinary event: it lands in the thread, in order, on every
        client, in the channel it belongs to.
        """
        pane_id = normalise_pane_id(pane)
        st = _store()
        data = await file.read()
        try:
            stored = await run_in_threadpool(
                images_mod.store, data, settings.image_root
            )
        except images_mod.ImageError as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
        except OSError as exc:
            raise HTTPException(
                status.HTTP_507_INSUFFICIENT_STORAGE, detail=f"could not store: {exc}"
            ) from exc

        shape = f"{stored.width}x{stored.height}" if stored.width else stored.media_type
        summary = caption.strip() or f"[image {shape}]"
        # ⚠️ Event is a FROZEN dataclass — assigning event.summary raises
        #    FrozenInstanceError AFTER the row is already written, which lands the
        #    image in the thread while the caller sees a 500 and no client is ever
        #    told. append() takes the summary; pass it, never patch it.
        event = st.append(
            pane_id,
            EventKind.IMAGE,
            caption.strip() or file.filename or "image",
            meta={"image": stored.to_dict(), "name": file.filename or ""},
            summary=summary,
        )
        app.state.broadcaster.publish({"type": "event", "event": event.to_dict()})
        return {"posted": stored.id, **stored.to_dict()}

    @app.get("/images/{image_id}", tags=["channels"],
             dependencies=[Depends(require_auth_flex)])
    async def get_image(image_id: str = PathParam(...)) -> FileResponse:
        """Serve stored bytes.

        ⚠️ Content-addressed, so these are immutable — an id can only ever mean one
        sequence of bytes. That is what makes the long cache header safe, and it is
        why clients may keep them forever.
        """
        try:
            path = await run_in_threadpool(
                images_mod.path_for, image_id, settings.image_root
            )
        except images_mod.ImageError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        media_type, _ = images_mod.sniff(path.read_bytes()[:16])
        return FileResponse(
            path,
            media_type=media_type,
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    @app.get("/intercom/state", tags=["channels"],
             dependencies=[Depends(require_auth_flex)])
    async def intercom_state() -> dict[str, Any]:
        """Who holds the floor, and how many audio frames each device sent/received.

        ★ Exists to answer one question without a second round of guessing: when
        talk-back does not arrive, is the talker not capturing, is the hub not
        relaying, or is the listener not playing? rx_frames on the talker and
        tx_frames on the sender separate all three.
        """
        ic: intercom_mod.Intercom = app.state.intercom
        return {
            **ic.snapshot(),
            "peers": sorted(app.state.intercom_peers),
            "stats": app.state.intercom_stats,
            "queued": {k: len(v) for k, v in app.state.queued.items()},
        }

    @app.websocket("/intercom/video")
    async def intercom_video(
        websocket: WebSocket,
        device: str = Query(..., min_length=1, max_length=64),
        token_q: str | None = Query(default=None, alias="token"),
    ) -> None:
        """Video frames, on their OWN socket.

        ⚠️⚠️ Separate from /intercom on purpose. A video frame is orders of magnitude
        bigger than a 640-byte audio frame, and on one socket it would head-of-line
        block the audio behind it — a monitor whose speech goes choppy whenever the
        picture updates is worse than one with no picture at all. Audio is the payload
        that must never stutter; video is the one that can drop a frame unnoticed.

        ★ NOT floor-governed. The floor is an echo rule and echo is an audio problem,
        so the room stays visible while someone talks back. The gate here is only
        "is this device's camera supposed to be on", which intercom.set_video owns.
        """
        header = websocket.headers.get("authorization", "")
        supplied = header[7:].strip() if header.lower().startswith("bearer ") else ""
        supplied = supplied or (token_q or "")
        if not supplied or not secrets.compare_digest(supplied, token):
            await websocket.accept()
            await websocket.send_json({"type": "error", "detail": "unauthorised"})
            await websocket.close(code=4401)
            return

        await websocket.accept()
        ic: intercom_mod.Intercom = app.state.intercom
        peers: dict[str, WebSocket] = app.state.video_peers
        peers[device] = websocket
        try:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                raw = message.get("bytes")
                if raw is None:
                    continue
                # ⚠️ Same rule as audio: the SERVER decides whether these bytes travel.
                #    A client whose camera was switched off remotely is not trusted to
                #    stop sending, and a picture that keeps arriving after it was
                #    turned off is the failure that matters here.
                if not ic.video_should_relay(device):
                    st = app.state.intercom_stats.setdefault(
                        device, {"rx_frames": 0, "rx_bytes": 0, "tx_frames": 0,
                                 "tx_bytes": 0, "dropped_no_floor": 0})
                    st["dropped_no_floor"] += 1
                    continue
                # ⚠️ TAG THE SOURCE. Frames were anonymous, so a client could only
                #    show "the newest blob" — and with the sender's continuous feed and
                #    a talker's burst both live they land in one slot and flicker
                #    between two cameras. It is also why a burst LOOKED FROZEN when it
                #    ended: nothing said which picture had stopped, so the last frame
                #    just sat there.
                #    [1 byte id length][id utf8][jpeg]
                ident = device.encode("utf-8")[:255]
                tagged = bytes([len(ident)]) + ident + raw
                for other, sock in list(peers.items()):
                    if other == device:
                        continue
                    try:
                        await sock.send_bytes(tagged)
                    except (WebSocketDisconnect, RuntimeError):
                        peers.pop(other, None)
        except WebSocketDisconnect:
            pass
        finally:
            peers.pop(device, None)

    @app.websocket("/intercom")
    async def intercom_endpoint(
        websocket: WebSocket,
        device: str = Query(..., min_length=1, max_length=64),
        role: str = Query(default="receiver"),
        token_q: str | None = Query(default=None, alias="token"),
    ) -> None:
        """Two-way audio, half-duplex by design.

        ★ One device opens a channel and streams; any number receive; a receiver
        holding PTT INTERRUPTS the feed and pushes the other way. Because the two
        directions never overlap there is no echo path, so no AEC -- that is the
        whole reason for this shape. See intercom.py.

        ⚠️⚠️ THE ENFORCEMENT THAT MATTERS: audio from a device that does not hold the
        floor is DROPPED HERE, silently. A client is not trusted to stop sending when
        it loses the floor -- a laggy release, a wedged press or an old build would
        otherwise put two live speakers in one house, which howls. The server is the
        only thing that decides whose bytes get relayed.
        """
        header = websocket.headers.get("authorization", "")
        supplied = header[7:].strip() if header.lower().startswith("bearer ") else ""
        supplied = supplied or (token_q or "")
        if not supplied or not secrets.compare_digest(supplied, token):
            await websocket.accept()
            await websocket.send_json({"type": "error", "detail": "unauthorised"})
            await websocket.close(code=4401)
            return

        await websocket.accept()
        ic: intercom_mod.Intercom = app.state.intercom
        peers: dict[str, WebSocket] = app.state.intercom_peers
        peers[device] = websocket

        async def announce() -> None:
            snap = {"type": "floor", **ic.snapshot()}
            for other, sock in list(peers.items()):
                try:
                    await sock.send_json(snap)
                except (WebSocketDisconnect, RuntimeError):
                    peers.pop(other, None)

        if role == "sender":
            ic.open_channel(device)
        else:
            ic.join(device)
        await announce()

        try:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break

                if (raw := message.get("bytes")) is not None:
                    st = app.state.intercom_stats.setdefault(
                        device, {"rx_frames": 0, "rx_bytes": 0, "tx_frames": 0,
                                 "tx_bytes": 0, "dropped_no_floor": 0}
                    )
                    st["rx_frames"] += 1
                    st["rx_bytes"] += len(raw)
                    # ⚠️ The gate. Not a client's decision.
                    if ic.expire():
                        await announce()
                    if ic.holder() != device:
                        st["dropped_no_floor"] += 1
                        continue
                    if device == ic.sender:
                        ic.touch_sender()
                    for other, sock in list(peers.items()):
                        if other == device:
                            continue
                        try:
                            await sock.send_bytes(raw)
                            ost = app.state.intercom_stats.setdefault(
                                other, {"rx_frames": 0, "rx_bytes": 0, "tx_frames": 0,
                                        "tx_bytes": 0, "dropped_no_floor": 0}
                            )
                            ost["tx_frames"] += 1
                            ost["tx_bytes"] += len(raw)
                        except (WebSocketDisconnect, RuntimeError):
                            peers.pop(other, None)
                    continue

                text = message.get("text")
                if text is None:
                    continue
                try:
                    control = json.loads(text)
                except ValueError:
                    continue
                kind = control.get("type")
                try:
                    if kind == "press":
                        ic.press(device)
                    elif kind == "release":
                        ic.release(device)
                    elif kind == "open":
                        ic.open_channel(device)
                    elif kind == "close":
                        ic.close_channel(device)
                    elif kind == "video":
                        # target defaults to the sender: "receiver can turn on sender
                        # video" is the common case and should not need naming.
                        ic.set_video(
                            control.get("target") or (ic.sender or device),
                            bool(control.get("on", True)),
                            by=device,
                            facing=str(control.get("facing") or "back"),
                        )
                    else:
                        continue
                except intercom_mod.IntercomError as exc:
                    await websocket.send_json({"type": "denied", "detail": str(exc)})
                    continue
                await announce()
        except WebSocketDisconnect:
            pass
        finally:
            peers.pop(device, None)
            if ic.sender == device:
                ic.close_channel(device)
            else:
                ic.leave(device)
            await announce()

    @app.websocket("/ws")
    async def websocket_endpoint(
        websocket: WebSocket,
        since: int | None = Query(default=None, ge=0),
        token_q: str | None = Query(default=None, alias="token"),
    ) -> None:
        header = websocket.headers.get("authorization", "")
        supplied = header[7:].strip() if header.lower().startswith("bearer ") else ""
        supplied = supplied or (token_q or "")
        if not supplied or not secrets.compare_digest(supplied, token):
            # 4401: application-level "unauthorised". The handshake has to be
            # accepted before a close frame carries a reason, so do that first.
            await websocket.accept()
            await websocket.send_json({"type": "error", "detail": "unauthorised"})
            await websocket.close(code=4401)
            return

        st = _store()
        await websocket.accept()
        with app.state.broadcaster.subscribe() as sub:
            watermark = st.latest_event_id()
            try:
                live = await run_in_threadpool(channels_mod.list_channels)
            except TmuxError:
                live = []
            await websocket.send_json(
                {
                    "type": "hello",
                    "protocol": PROTOCOL_VERSION,
                    "version": HUB_VERSION,
                    "server_time": time.time(),
                    "latest_event_id": watermark,
                    "channels": build_channel_list(st, live),
                    "presence": app.state.presence.snapshot(),
                }
            )
            if since is not None:
                backlog = st.events_since(since)
                await websocket.send_json(
                    {
                        "type": "backlog",
                        "since": since,
                        "events": [e.to_dict(INLINE_BODY_CHARS) for e in backlog],
                    }
                )
                if backlog:
                    watermark = max(watermark, backlog[-1].id)

            reader = asyncio.create_task(_client_pump(websocket, sub))
            try:
                while True:
                    if sub.overflowed:
                        await websocket.send_json(
                            {"type": "desync", "latest_event_id": st.latest_event_id()}
                        )
                        await websocket.close(code=1011)
                        return
                    try:
                        message = await asyncio.wait_for(
                            sub.queue.get(), timeout=HEARTBEAT_SECONDS
                        )
                    except asyncio.TimeoutError:
                        if reader.done():
                            return
                        await websocket.send_json({"type": "ping", "t": time.time()})
                        continue
                    if message.get("type") == "event":
                        event_id = message["event"]["id"]
                        if event_id <= watermark:
                            continue  # already replayed in the backlog
                        watermark = event_id
                    await websocket.send_json(message)
            except (WebSocketDisconnect, RuntimeError):
                return
            finally:
                reader.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await reader

    return app


async def _client_pump(websocket: WebSocket, sub: _Subscriber) -> None:
    """Read client frames. Only one writer touches the socket, so replies go
    back through the subscriber queue rather than being sent from here."""
    while True:
        message = await websocket.receive_json()
        if isinstance(message, dict) and message.get("type") == "ping":
            sub.offer({"type": "pong", "t": time.time()})


# ------------------------------------------------------------------- poller


def _remember_all(store: Store, live: list[Channel]) -> None:
    for ch in live:
        store.remember_channel(ch.pane_id, ch.label, ch.session)


def _sample_activity(
    store: Store,
    live: list[Channel],
    digests: dict[str, str],
    now: float,
    screens: dict[str, str] | None = None,
) -> dict[str, float]:
    """Hash every live pane's screen; record the ones that changed.

    Runs in a worker thread -- one small `capture-pane` per pane per poll.
    Returns `{pane_id: timestamp}` for panes whose output moved, which is what
    gets pushed as the liveness heartbeat.
    """
    screens = {} if screens is None else screens
    moved: dict[str, float] = {}
    for ch in live:
        content = channels_mod.screen(ch.pane_id)
        if not content:
            continue
        digest = hashlib.sha1(content.encode("utf-8", "replace")).hexdigest()
        previous = digests.get(ch.pane_id)
        digests[ch.pane_id] = digest
        # ★ Prompt detection rides the SAME capture as the liveness hash, and only
        #   when the screen actually moved: a selector cannot appear or disappear
        #   without the screen changing, so this adds no tmux calls at all.
        if previous != digest:
            screens[ch.pane_id] = content
        # A pane we have never sampled counts as active now: it is the best
        # reading available, and claiming "idle for hours" would be a lie.
        if previous is None or previous != digest:
            store.set_channel_activity(ch.pane_id, now)
            moved[ch.pane_id] = now
    for pane_id in set(digests) - {c.pane_id for c in live}:
        digests.pop(pane_id, None)
    return moved


async def _flush_when_ready(app: FastAPI, pane_id: str) -> None:
    """Send what was held, once the pane is actually listening.

    ⚠️⚠️ The whole reason this is not a plain loop at the end of /respond: a pane
    whose gate just cleared is still drawing, and `send-keys` into it succeeds and
    is discarded. Measured on a live pane -- "flushed: 1", 0 occurrences in the
    scrollback. Waiting for two identical screens is the difference between a queue
    that protects his words and one that eats them more politely than before.
    """
    store: Store = app.state.store
    broadcaster: Broadcaster = app.state.broadcaster
    ready = await run_in_threadpool(channels_mod.settled, pane_id)
    held = app.state.queued.pop(pane_id, [])
    if not held:
        return
    if not ready:
        app.state.queued.setdefault(pane_id, []).extend(held)
        log.warning("pane %s never settled; %d message(s) still held",
                    pane_id, len(held))
        return
    for i, text in enumerate(held):
        try:
            await run_in_threadpool(channels_mod.send, pane_id, text, True)
        except (TmuxError, ValueError) as exc:
            # Never silently eat them: put the rest back and say so in the thread.
            app.state.queued.setdefault(pane_id, []).extend(held[i:])
            event = store.append(
                pane_id,
                EventKind.ERROR,
                f"held message could not be sent: {exc}",
                meta={"attempted": text},
            )
            broadcaster.publish({"type": "event", "event": event.to_dict()})
            return


def _watch_prompts(
    app: FastAPI,
    store: Store,
    broadcaster: Broadcaster,
    screens: dict[str, str],
    open_prompts: dict[str, str],
) -> None:
    """Notice a pane asking a question, and notice when it stops.

    ★ The prompt is LIVE STATE, not only history: `app.state.prompts` is what a
    client renders as buttons, and it is cleared the moment the selector leaves the
    screen -- an answered question must stop being answerable, including when it was
    answered at the keyboard rather than from a client.
    ★ An event is appended too, so the thread still shows that the question happened
    after it is gone.

    ⚠️ Keyed on the prompt's fingerprint, which excludes the cursor position, so
    arrowing up and down a menu at the keyboard does not emit a storm of events.
    """
    prompts_state: dict[str, dict] = app.state.prompts
    for pane_id, content in screens.items():
        found = prompts_mod.parse(content)
        previous = open_prompts.get(pane_id)

        if found is None:
            if previous is not None:
                open_prompts.pop(pane_id, None)
                prompts_state.pop(pane_id, None)
                broadcaster.publish(
                    {"type": "prompt", "pane": pane_id, "prompt": None}
                )
            continue

        if found.fingerprint == previous:
            # same question, cursor may have moved -- refresh the selection only
            prompts_state[pane_id] = found.to_dict()
            continue

        open_prompts[pane_id] = found.fingerprint
        prompts_state[pane_id] = found.to_dict()
        event = store.append(
            pane_id,
            EventKind.PROMPT,
            found.summary(),
            meta={"prompt": found.to_dict()},
        )
        broadcaster.publish({"type": "event", "event": event.to_dict()})
        broadcaster.publish(
            {"type": "prompt", "pane": pane_id, "prompt": found.to_dict()}
        )

    # a pane that vanished takes its question with it
    for pane_id in set(open_prompts) - set(screens):
        if not channels_mod.exists(pane_id):
            open_prompts.pop(pane_id, None)
            prompts_state.pop(pane_id, None)


async def _poll_forever(app: FastAPI) -> None:
    """Watch tmux so clients never have to.

    The client holding a WebSocket must not poll -- an idle socket costs less
    than repeated wake/handshake/teardown and delivers instantly. Something
    still has to notice panes opening and closing, so the hub does it once,
    locally, for every client.
    """
    settings: Settings = app.state.settings
    store: Store = app.state.store
    broadcaster: Broadcaster = app.state.broadcaster
    presence: Presence = app.state.presence
    known: dict[str, str] | None = None  # pane_id -> label
    digests: dict[str, str] = {}  # pane_id -> last screen fingerprint
    open_prompts: dict[str, str] = {}  # pane_id -> fingerprint of the live selector
    while True:
        try:
            # ★ Adopt anything written straight to the ledger while this process
            # was not running. Nothing pushed those: the bridge subscribes to
            # this hub, so when the hub is down the bridge is deaf. Publishing
            # them now puts them on the ordinary push path, and clearing the
            # flag in the same claim means they can never buzz twice.
            #
            # Ahead of the tmux call on purpose -- a box without tmux still owes
            # him the message.
            for orphan in store.claim_pending():
                log.warning(
                    "adopting a %s written while the hub was down: %s",
                    orphan.kind,
                    orphan.summary or orphan.body[:80],
                )
                broadcaster.publish(
                    {"type": "event", "event": orphan.to_dict(INLINE_BODY_CHARS)}
                )

            try:
                live = await run_in_threadpool(channels_mod.list_channels)
                app.state.tmux_ok = True
            except TmuxError as exc:
                if app.state.tmux_ok:
                    log.warning("tmux unavailable: %s", exc)
                app.state.tmux_ok = False
                await asyncio.sleep(settings.poll_interval)
                continue

            app.state.live_channels = live
            current = {c.pane_id: c.label for c in live}
            changed = known is None or current != known

            for ch in live:
                first_time = store.get_channel(ch.pane_id) is None
                store.remember_channel(ch.pane_id, ch.label, ch.session)
                if first_time:
                    event = store.append(
                        ch.pane_id,
                        EventKind.OPENED,
                        ch.label,
                        meta={"session": ch.session},
                    )
                    broadcaster.publish({"type": "event", "event": event.to_dict()})

            if known:
                for pane_id, label in known.items():
                    if pane_id not in current:
                        event = store.append(
                            pane_id,
                            EventKind.CLOSED,
                            f"channel closed ({label})",
                        )
                        broadcaster.publish(
                            {"type": "event", "event": event.to_dict()}
                        )

            # Presence is reported, not observed, so the poller only has to
            # expire what has lapsed and say so when that changes anything.
            before = presence.signature()
            presence.sweep()
            if presence.signature() != before:
                broadcaster.publish({"type": "presence", **presence.snapshot()})

            if settings.activity_polling and live:
                screens: dict[str, str] = {}
                moved = await run_in_threadpool(
                    _sample_activity, store, live, digests, time.time(), screens
                )
                _watch_prompts(app, store, broadcaster, screens, open_prompts)
                if moved:
                    broadcaster.publish(
                        {
                            "type": "activity",
                            "panes": moved,
                            "server_time": time.time(),
                        }
                    )

            if changed:
                broadcaster.publish(
                    {
                        "type": "channels",
                        "channels": build_channel_list(store, live),
                        "server_time": time.time(),
                    }
                )
            known = current
        except asyncio.CancelledError:
            raise
        except Exception:  # a poller crash must not take the hub down
            log.exception("channel poller error")
        await asyncio.sleep(settings.poll_interval)


def main() -> None:
    import uvicorn

    settings = Settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    token_source = "ROAM_HUB_TOKEN" if settings.token else str(settings.token_file)
    resolve_token(settings)
    log.info(
        "roam-hub %s listening on http://%s:%s (db %s, token %s)",
        HUB_VERSION,
        settings.host,
        settings.port,
        settings.db_path,
        token_source,
    )
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        ws_ping_interval=20.0,
        ws_ping_timeout=60.0,
    )


if __name__ == "__main__":
    main()
