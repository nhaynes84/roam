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
import difflib
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
    Request,
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

import apps as apps_mod
import channels as channels_mod
import cron as cron_mod
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


#: How long a peer gets to accept one 20ms audio frame before it is dropped for
#: being slow. Deliberately about one frame time: a frame that misses its slot is
#: already stale, and holding it only pushes the delay further out.
RELAY_DEADLINE_S = 0.05


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

    #: ★★ How soon after the hub types into a pane a receipt is certainly its echo.
    #:
    #: ⚠️ The matching used to be LOOSE ON TIME (60s) and STRICT ON TEXT (exact), which
    #: is backwards: the clock is the reliable signal and the text is the corrupted one.
    #: The path is hub -> types into a tmux pane -> the agent's hook reports what it
    #: saw, and that terminal is lossy -- it has expanded tabs to four spaces and
    #: dropped a trailing character, each time breaking equality and drawing his
    #: message twice. A real echo lands in about 100ms (observed: events 4054/4055,
    #: 0.1s apart), so inside this window the text may differ and it is still the echo.
    #: A false match would need him to hand-type a near-identical message within two
    #: seconds of the app sending one.
    echo_certain_s: float = 2.0

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
    #: ⚠️ WHO is asking, so one person cannot reach into the other's private
    #: sessions -- owner: *"she shouldn't be able to manage my sessions or me
    #: hers."* An organisational hint like everywhere else, defaulting to the hub
    #: owner so every existing client keeps working untouched.
    user: str | None = None
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

    #: ⚠️ WHO is asking, so one person cannot reach into the other's private
    #: sessions -- owner: *"she shouldn't be able to manage my sessions or me
    #: hers."* An organisational hint like everywhere else, defaulting to the hub
    #: owner so every existing client keeps working untouched.
    user: str | None = None
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
    #: ★ Who this channel belongs to, or "shared" for one both people work in.
    #: None leaves the pane unowned, which is what a hand-opened pane looks like
    #: and reads as the hub owner's.
    owner: str | None = None


class KillRequest(BaseModel):
    origin: str = "client"
    #: ⚠️ WHO is asking, so one person cannot reach into the other's private
    #: sessions -- owner: *"she shouldn't be able to manage my sessions or me
    #: hers."* An organisational hint like everywhere else, defaulting to the hub
    #: owner so every existing client keeps working untouched.
    user: str | None = None



class LabelRequest(BaseModel):
    """Rename a channel."""

    label: str = Field(min_length=1, max_length=80)
    user: str | None = None


class ReadRequest(BaseModel):
    """How far this person has read a channel."""

    cursor: int = Field(ge=0)
    user: str | None = None


class OwnerRequest(BaseModel):
    """Hand a channel to someone, or share it with everyone."""

    #: A name, "shared", or "" to leave it unowned. Owner: *"shared channels for
    #: trips and stuff where we can both collab."*
    owner: str = ""
    user: str | None = None


class ArchiveRequest(BaseModel):
    archived: bool = True


class CronJobRequest(BaseModel):
    """Create or replace a scheduled job."""

    name: str = Field(default="", max_length=120)
    kind: str = Field(description="Schedule kind: 'at', 'every' or 'cron'.")
    expr: str = Field(
        min_length=1,
        description="ISO timestamp / '20m' for at; '10m'/'1h'/'1d' for every; a "
        "5- or 6-field cron expression for cron.",
    )
    tz: str = Field(default="", max_length=64, description="IANA tz for cron/at.")
    pane_id: str = Field(default="", description="Channel to fire the prompt into.")
    prompt: str = Field(default="", description="What to send when it fires.")
    delivery: str = Field(default="channel", description="channel | notify | none.")
    owner: str | None = None
    enabled: bool = True
    delete_after_run: bool = False


class CronPatchRequest(BaseModel):
    """Edit fields of a job; every field optional (only what is sent changes)."""

    name: str | None = None
    kind: str | None = None
    expr: str | None = None
    tz: str | None = None
    pane_id: str | None = None
    prompt: str | None = None
    delivery: str | None = None
    enabled: bool | None = None
    delete_after_run: bool | None = None


class RespondRequest(BaseModel):
    """Choose one option on a pane's open selector."""

    #: ⚠️ WHO is asking, so one person cannot reach into the other's private
    #: sessions -- owner: *"she shouldn't be able to manage my sessions or me
    #: hers."* An organisational hint like everywhere else, defaulting to the hub
    #: owner so every existing client keeps working untouched.
    user: str | None = None
    option: int = Field(ge=1, le=12, description="The option number, as displayed.")


class ShareRequest(BaseModel):
    """Hand a browsed file to Claude.

    `path` is a browse path (`CAD/estack/drum_lh.step`), never a filesystem
    path -- see `files.resolve`. The file is *copied* into the dropzone inbox;
    nothing in the shared folders is ever moved or changed.
    """

    path: str = Field(min_length=1, max_length=1024)
    #: Which person's roots and inbox this share is against.
    user: str | None = None


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


def channel_status(
    live: bool, last_kind: str | None, pane_id: str | None = None,
    asking: bool = False,
) -> str:
    """`dead` | `asking` | `working` | `idle` -- what the panel puts on the chip."""
    if not live:
        return "dead"
    # ★ A live open question outranks working and idle: the channel is waiting on HIM,
    #   and that has to read differently from "idle -- your move is optional" and from
    #   "working -- leave it alone". Driven by app.state.prompts (screen-truth), so it
    #   clears the instant the selector leaves the screen.
    if asking:
        return "asking"
    if last_kind in (EventKind.SENT.value, EventKind.RECEIPT.value):
        # ⚠️ Only "working" if the agent is TRULY mid-reply. A message received but
        #    producing no closing outcome event (a rapid-send burst, a Stop that
        #    extracted nothing) would otherwise leave the chip spinning "working"
        #    forever -- the stuck state seen on her channels.
        if pane_id is not None and not channels_mod.busy(pane_id):
            return "idle"
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
        # ⚠️ Every channel row carries an owner, including this one. A client that
        #    reads `c["owner"]` should never have to special-case one row — the host
        #    channel is unowned, which is a value, not an absence.
        "owner": "",
        "shared": False,
    }


def channel_view(
    store: Store,
    pane_id: str,
    live: Channel | None,
    stored: StoredChannel | None,
    asking_panes: set[str] | None = None,
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
        "status": channel_status(
            live is not None, last.kind if last else None, pane_id,
            asking=asking_panes is not None and pane_id in asking_panes,
        ),
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
        # ★★ WHICH DEVICE last spoke here — derived from the last `sent`, not stored
        #    alongside it. `last_input_source` only says app-vs-tmux, and his Mac and
        #    his phone are both "app"; telling them apart is the whole notification
        #    question, and the ledger already answered it.
        "last_input_origin": store.last_origin(pane_id),
        "event_count": store.event_count(pane_id),
        "last_event": last.to_dict(INLINE_BODY_CHARS) if last else None,
        # ⚠️ The LIVE pane wins, but a dead channel falls back to what we
        #    remembered -- a pane's options die with the pane, and a finished
        #    session must not silently become unowned and drop off its owner's
        #    list. Empty means unowned, which reads as the hub owner's.
        "owner": (live.owner if live and live.owner
                  else (stored.owner if stored else "")),
    }


def build_channel_list(
    store: Store,
    live_channels: list[Channel],
    include_archived: bool = False,
    asking_panes: set[str] | None = None,
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
        views.append(
            channel_view(store, pane_id, live_by_id.get(pane_id), stored, asking_panes)
        )
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
        # ★★ Many streams now, not one channel. Each carries its own floor so
        #    talking on one says nothing about the others -- owner: *"i want to talk
        #    to my wife without disrupting my son."*
        app.state.streams = intercom_mod.Streams()
        # Peers keyed by (stream, device): the same laptop can be a monitor on the
        # kitchen stream and a source on another, and one socket per pair keeps
        # those from overwriting each other.
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
        #: The scheduler: fires cron_jobs into their channels on time. Separate
        #: task from the poller so a slow tmux poll never delays a due job and a
        #: scheduler stall never freezes liveness.
        app.state.scheduler = asyncio.create_task(cron_mod.run_scheduler(app))
        try:
            yield
        finally:
            app.state.poller.cancel()
            app.state.scheduler.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await app.state.poller
            with contextlib.suppress(asyncio.CancelledError):
                await app.state.scheduler
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

    def _text_similar(a: str, b: str) -> bool:
        """Close enough to be the same message mangled in transit.

        ⚠️ SIMILARITY, not prefix. A prefix rule was tried and rejected the same
        minute: "run the tests" is a prefix of "run the tests again please", so a
        message he genuinely typed would have been swallowed as an echo of a shorter
        one — and a receipt wrongly marked as an echo VANISHES rather than doubling.

        The two corruptions actually observed both score far above this bar: tabs
        expanded to four spaces measured 0.93, and a dropped trailing character on a
        175-character message is 0.997. The false case above is 0.67.
        """
        if not a or not b:
            return False
        if difflib.SequenceMatcher(None, a, b).ratio() >= 0.85:
            return True
        # ⚠️ A TRUNCATED CAPTURE. Observed 2026-08-26: a 1320-character message came
        #    back as its last 298 characters, cut mid-word, so similarity was 0.37 and
        #    the fragment rendered as a second message "typed in tmux". A contiguous
        #    substring of what we just sent is not something he typed by hand.
        #
        # ⚠️ Direction matters: the REPORTED text must be contained in the SENT text,
        #    never the other way round. "run the tests" sent and "run the tests again
        #    please" reported is him adding to it, and swallowing that would lose a
        #    real message. The length floor keeps a short coincidence out.
        return False

    def _echo_matches(sent: str, reported: str, age_s: float = 0.0) -> bool:
        """Whether `reported` is the pane echoing `sent` back at us.

        ⚠️⚠️ NOT equality, and this is the SECOND way equality has failed. The first
        was tab expansion (see `_echo_key`). The second, observed on events 4039/4040:
        the receipt came back a **prefix** of what was sent, one character short --
        a trailing `;` simply missing. The keys therefore differed, the receipt was not
        recognised as an echo, and the thread drew his message twice.

            sent     '...preload any profile stuff;'   (175 chars)
            reported '...preload any profile stuff'    (174 chars)

        ★ So a short truncated tail counts as a match. The tolerance is deliberately
        TINY, because the dangerous direction is the other one: a receipt wrongly
        marked as an echo stops being the record that he typed something, and the
        message disappears rather than doubling. Doubling is a nuisance; vanishing is
        data loss.

        The guard rails that make this safe: it is only ever compared against the
        SINGLE most recent `sent` in the SAME pane inside the echo window, the shared
        prefix must be long enough not to be a coincidence, and at most two characters
        may be missing.
        """
        a, b = _echo_key(sent), _echo_key(reported)
        if a == b:
            return True
        # ⚠️ FULL text, not the 200-character key, for the containment test below: the
        #    fragment that failed was the TAIL of a 1320-character message, and a tail
        #    can never be found inside a key that stops at character 200.
        whole_sent = " ".join((sent or "").split())
        whole_reported = " ".join((reported or "").split())
        # ★ Inside the certain window the clock has already answered the question, so
        #   the text only has to be recognisable. Outside it, fall back to exactness:
        #   a busy pane can echo late, and a late receipt that merely resembles an
        #   older send is far more likely to be him retyping.
        if age_s > settings.echo_certain_s:
            return False
        if _text_similar(a, b):
            return True
        # ⚠️ A TRUNCATED CAPTURE. Observed 2026-08-26: a 1320-character message came
        #    back as its last 298 characters, cut mid-word, so similarity was 0.37 and
        #    the fragment rendered as a second message "typed in tmux". A contiguous
        #    run of what we just sent is not something he typed by hand.
        #
        # ⚠️ DIRECTION MATTERS: the reported text must sit inside the SENT text, never
        #    the other way round. "run the tests" sent and "run the tests again please"
        #    reported is him adding to it, and swallowing that would lose a real
        #    message. The length floor keeps a short coincidence out.
        return (
            len(whole_reported) >= 40
            and len(whole_reported) < len(whole_sent)
            and whole_reported in whole_sent
        )

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
        now = time.time()
        cutoff = now - settings.echo_window_s
        for event in reversed(recent):
            if event.kind != EventKind.SENT.value or event.ts < cutoff:
                continue
            if not typed or _echo_matches(event.body, typed, age_s=now - event.ts):
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

    async def _require_manage(pane_id: str, user: str | None) -> None:
        """Refuse to touch a channel that is not this caller's to touch.

        ★★ THE ONE BOUNDARY HE ASKED TO BE ENFORCED: *"she shouldn't be able to
        manage my sessions or me hers."* Everything else in the profiles work is
        tidiness; this is the part with teeth.

        ⚠️ Shared channels are managed by BOTH -- that is what sharing one means.
        ⚠️ 404, not 403: confirming that a private channel exists is itself the
        leak. A pane that is not yours is a pane that is not there.
        """
        st = _store()
        live = await _live_channels()
        match = next((c for c in live if c.pane_id == pane_id), None)
        stored = st.get_channel(pane_id)
        if match is None and stored is None:
            return  # the route's own 404 has a better message
        view = channel_view(st, pane_id, match, stored)
        if not _visible_to(view, user):
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail=f"unknown channel: {pane_id}"
            )

    @app.get("/channels", tags=["channels"], dependencies=[Depends(require_auth)])
    async def list_channels_endpoint(
        include_archived: bool = Query(False),
        user: str | None = Query(None, max_length=64),
    ) -> dict[str, Any]:
        """The channels this client should see.

        ★ Owner: *"shared channels for trips and stuff where we can both collab."*
        A shared channel is on both lists; a private one is on its owner's; an
        UNOWNED pane -- every pane he has ever opened by hand -- stays on his.

        ⚠️ `user` is an organisational hint, not a credential, exactly like the Apps
        shelf. It picks whose list to draw. Omitting it yields the owner's, which is
        what every existing client does and must keep doing.
        """
        live = await _live_channels()
        st = _store()
        await run_in_threadpool(_remember_all, st, live)
        rows = build_channel_list(st, live, include_archived, asking_panes=set(app.state.prompts))
        rows = [r for r in rows if _visible_to(r, user)]
        return {
            "channels": rows,
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
                request.owner,
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
                "channels": build_channel_list(st, all_live, asking_panes=set(app.state.prompts)),
                "server_time": time.time(),
            }
        )
        return {"channel": channel_view(st, pane_id, live, st.get_channel(pane_id))}

    @app.post(
        "/channels/{pane}/label",
        tags=["channels"],
        dependencies=[Depends(require_auth)],
    )
    async def set_label_endpoint(
        payload: LabelRequest, pane: str = PathParam(...)
    ) -> dict[str, Any]:
        """Rename a channel.

        ★ Owner: *"i need the ability to rename any channel."* Names came only from
        `spawn`, so anything opened by hand -- or named badly once -- was stuck with
        it forever.

        ⚠️ Written to the PANE and to the store. The pane option is the live truth; the
        store is what keeps the name once the pane dies, and a dead channel has no
        option left to read.
        """
        pane_id = normalise_pane_id(pane)
        await _require_manage(pane_id, payload.user)
        label = payload.label.strip()
        if not label:
            raise HTTPException(400, detail="a channel needs a name")

        st = _store()
        live = await _live_channels()
        match = next((c for c in live if c.pane_id == pane_id), None)
        if match is None and st.get_channel(pane_id) is None:
            raise HTTPException(404, detail=f"unknown channel: {pane_id}")
        if match is not None:
            try:
                await run_in_threadpool(channels_mod.set_label, pane_id, label)
            except TmuxError as exc:
                raise HTTPException(
                    status.HTTP_502_BAD_GATEWAY, detail=str(exc)
                ) from exc
        await run_in_threadpool(st.set_channel_label, pane_id, label)

        live = await _live_channels()
        match = next((c for c in live if c.pane_id == pane_id), None)
        view = channel_view(st, pane_id, match, st.get_channel(pane_id))
        _publish({"type": "channel", "channel": view})
        return {"channel": view}

    @app.post(
        "/channels/{pane}/read",
        tags=["channels"],
        dependencies=[Depends(require_auth_flex)],
    )
    async def mark_read_endpoint(
        payload: ReadRequest, pane: str = PathParam(...)
    ) -> dict[str, Any]:
        """Record how far this PERSON has read.

        ★★ Owner: *"i'm getting unread tag counts on threads I read on other
        devices."* Read state lived in each client's own settings, so reading a thread
        on the Mac left it bold on the phone. Unread is a fact about a person, not
        about a piece of hardware.
        """
        pane_id = normalise_pane_id(pane)
        who = (payload.user or channels_mod.DEFAULT_OWNER).strip().lower()
        cursor = await run_in_threadpool(
            _store().mark_read, who, pane_id, payload.cursor
        )
        return {"pane_id": pane_id, "user": who, "cursor": cursor}

    @app.get(
        "/read",
        tags=["channels"],
        dependencies=[Depends(require_auth_flex)],
    )
    async def read_cursors_endpoint(
        user: str | None = Query(None, max_length=64),
    ) -> dict[str, Any]:
        """Every channel this person has read, and how far."""
        who = (user or channels_mod.DEFAULT_OWNER).strip().lower()
        return {"user": who, "cursors": _store().read_cursors(who)}

    @app.post(
        "/channels/{pane}/owner",
        tags=["channels"],
        dependencies=[Depends(require_auth)],
    )
    async def set_owner_endpoint(
        payload: OwnerRequest, pane: str = PathParam(...)
    ) -> dict[str, Any]:
        """Give a channel an owner, or mark it shared.

        ★ This is how the December trip becomes a channel they both work in:
        `{"owner": "shared"}`. It is also how a channel spawned by hand gets
        claimed, since a hand-opened pane carries no option.

        ⚠️ Guarded like any other write: you cannot reassign a channel you cannot
        already manage, which is what stops one person quietly taking the other's.
        ⚠️ Written to the PANE and to the store. The pane option is the live truth;
        the store is what keeps it once the pane dies.
        """
        pane_id = normalise_pane_id(pane)
        await _require_manage(pane_id, payload.user)
        owner = payload.owner.strip().lower()
        live = await _live_channels()
        if any(c.pane_id == pane_id for c in live):
            try:
                await run_in_threadpool(channels_mod.set_owner, pane_id, owner)
            except TmuxError as exc:
                raise HTTPException(
                    status.HTTP_502_BAD_GATEWAY, detail=str(exc)
                ) from exc
        st = _store()
        stored = st.get_channel(pane_id)
        if stored is None and not any(c.pane_id == pane_id for c in live):
            raise HTTPException(404, detail=f"unknown channel: {pane_id}")
        await run_in_threadpool(st.set_channel_owner, pane_id, owner)
        match = next((c for c in live if c.pane_id == pane_id), None)
        # ★ Push the change so a newly-shared channel appears on the other person's
        #   client immediately, not only after they reconnect. A `channels` frame is
        #   narrowed per-socket by the WS pump, so this cannot leak a private channel.
        # ⚠️ Re-read live AFTER writing the owner: `live` above was captured before the
        #    pane option changed, so broadcasting it would send the channel with its OLD
        #    owner and the WS pump would filter it out for the person it was just shared
        #    with -- the share would silently never arrive.
        fresh = await _live_channels()
        app.state.broadcaster.publish(
            {"type": "channels", "channels": build_channel_list(st, fresh, asking_panes=set(app.state.prompts))}
        )
        return {"channel": channel_view(st, pane_id, match, st.get_channel(pane_id))}

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
        await _require_manage(pane_id, request.user)
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
        await _require_manage(pane_id, payload.user)
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
        await _require_manage(pane_id, payload.user)
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
        # ★ Shared channels carry two speakers, and the agent otherwise sees Nick's and
        #   Jeanne's messages as identical text -- so it guesses who is talking and gets
        #   it wrong. Prefix the sender's name so it always knows. Private channels are
        #   unambiguous (the owner), so their text is left exactly as typed.
        who = (payload.user or channels_mod.DEFAULT_OWNER).strip().capitalize()
        wire = f"{who}: {payload.text}" if live.shared else payload.text
        if pane_id in app.state.prompts:
            app.state.queued.setdefault(pane_id, []).append(wire)
            return {
                "queued": True,
                "pane": pane_id,
                "waiting_on": app.state.prompts[pane_id],
                "detail": "held until the open prompt is answered",
            }
        # ★ Don't type into a channel that's mid-reply: keystrokes sent while the
        #   agent is still drawing get dropped, which stranded messages as stale
        #   renders that never submitted. Hold it and flush when the reply finishes.
        #   Record the SENT event now so his words show in the thread immediately;
        #   the keystrokes land once the pane is free.
        if await run_in_threadpool(channels_mod.busy, pane_id):
            st.remember_channel(pane_id, live.label, live.session)
            st.set_channel_input(pane_id, INPUT_APP)
            held_event = st.append(
                pane_id, EventKind.SENT, wire,
                meta={"origin": payload.origin, "enter": payload.enter, "held": True},
            )
            _publish_event(held_event)
            app.state.queued.setdefault(pane_id, []).append(wire)
            return {
                "event": held_event.to_dict(),
                "queued": True,
                "channel": channel_view(st, pane_id, live, st.get_channel(pane_id)),
            }
        try:
            await run_in_threadpool(
                channels_mod.send, pane_id, wire, payload.enter
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
            wire,
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
        await _require_manage(pane_id, request.user)
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
                original = st.get_event(echo_of)
                meta = {**(meta or {}), "echo_of": echo_of}
                # ★★ SOURCE, uniformly. An echo did not originate at the keyboard --
                #    it originated on whichever device sent the message it duplicates,
                #    and saying so makes the ledger answer "who said this" without
                #    anybody re-deriving it from `echo_of`.
                if original is not None:
                    meta["origin"] = (original.meta or {}).get("origin", "app")
                    # ⚠️ WHAT CAME BACK IS NOT WHAT WENT OUT. The terminal is a lossy
                    #    channel: it has expanded tabs to four spaces and dropped a
                    #    trailing character. Cosmetic for prose, but a Makefile or a
                    #    TSV sent through a channel arrives altered and nothing said
                    #    so. Now the ledger records it.
                    # ⚠️ RAW bodies, not echo keys. The key normalises runs of
                    #    whitespace to single spaces, which is exactly the corruption
                    #    being looked for — comparing keys made the check blind to the
                    #    tab expansion it exists to catch.
                    if (original.body or "") != (payload.body or ""):
                        meta["transit_altered"] = True
                        log.warning(
                            "pane %s: text altered in transit (sent %d chars, "
                            "echoed %d) -- tabs or trailing characters lost",
                            pane_id, len(original.body or ""), len(payload.body or ""),
                        )
            else:
                # Nothing to echo: he typed it at the keyboard.
                meta = {**(meta or {}), "origin": "tmux"}
        elif payload.kind in (EventKind.OUTCOME.value, EventKind.ERROR.value,
                              EventKind.NOTE.value):
            # The agent in the pane produced it.
            meta = {**(meta or {}), "origin": (meta or {}).get("origin", "agent")}
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

    # ---------------------------------------------------------------- apps
    #
    # ★ The shelf. `apps.py` decides WHAT is on it and for WHOM; these two routes
    # add the only things that need the machine: is it answering, and start it.
    #
    # ★★ A tile is a host, not a link. Owner: *"these sites don't just run all the
    # time and keeping track of them in chrome is challenging."* So the shelf reports
    # liveness, and a dead tile is one tap from being a live one.

    def _app_is_live(port: int, timeout: float = 0.35) -> bool:
        """Whether something is listening. A connect, not a GET.

        ⚠️ Deliberately not an HTTP request: EnCountAble answers `/` with a 307 to
        the picker, a login-walled app answers 401, and both are "up". The question
        the shelf asks is whether the port is open, and nothing more.
        ⚠️ Short timeout because this runs once per hosted tile on every shelf
        fetch, and a hung probe would stall the whole home screen.
        """
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=timeout):
                return True
        except OSError:
            return False

    @app.get("/apps", tags=["apps"], dependencies=[Depends(require_auth_flex)])
    async def list_apps(
        request: Request,
        user: str | None = Query(None, max_length=64),
    ) -> dict[str, Any]:
        """This caller's shelf.

        ⚠️ `user` is an ORGANISATIONAL hint, not a credential -- owner: *"encountable
        doesn't need to be locked down, we infer 'her data / version' based on 'HER
        nexus'."* It says which shelf to draw; it does not gate anything, and the
        bearer token is still what gets you in the door.
        """
        shelf = apps_mod.visible_for(user)
        # ★ The host the client actually reached us on, so the URL it is handed
        #   works from where it is standing. See `apps.url_for`.
        host = request.url.hostname or settings.host
        rows = []
        for entry in shelf:
            live = None
            if entry.hosted:
                # ★ A tile served BY the hub (its own port) is up whenever the hub
                #   is answering -- which it is, since this request reached it. The
                #   `_app_is_live` probe hits 127.0.0.1, but the hub binds only the
                #   tailnet address, so probing itself falsely reads "down".
                if entry.port == settings.port:
                    live = True
                else:
                    live = await run_in_threadpool(_app_is_live, entry.port)
            rows.append(apps_mod.to_json(entry, host, live))
        return {"apps": rows}

    @app.post(
        "/apps/{app_id}/start", tags=["apps"],
        dependencies=[Depends(require_auth_flex)],
    )
    async def start_app(
        request: Request,
        app_id: str = PathParam(..., max_length=64),
    ) -> dict[str, Any]:
        """Bring a hosted app up, and say whether it came up.

        ⚠️ `kickstart` rather than `bootstrap`: the job is already loaded (KeepAlive),
        so bootstrap would fail with "service already loaded" on the common path.
        ⚠️ The launchd label comes from the REGISTRY, never from the URL -- `app_id`
        is looked up, so there is no arrangement of path characters that reaches
        launchctl with an attacker's string.
        """
        entry = apps_mod.find(app_id)
        if entry is None or not entry.hosted:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no such app")

        def _kickstart() -> None:
            subprocess.run(
                ["launchctl", "kickstart", f"gui/{os.getuid()}/{entry.service}"],
                capture_output=True, timeout=15,
            )

        await run_in_threadpool(_kickstart)
        # Next.js needs a moment between "process exists" and "port is open".
        for _ in range(20):
            if await run_in_threadpool(_app_is_live, entry.port):
                break
            await asyncio.sleep(0.25)

        host = request.url.hostname or settings.host
        live = await run_in_threadpool(_app_is_live, entry.port)
        return apps_mod.to_json(entry, host, live)

    # ★★ Per-user Files roots. Owner: *"she doesn't need to see my Files app ... give
    #    her her own shared folders from talos."* His Files were global — she saw his
    #    CAD and Photos. Now each person's roots are their own, and the browser is
    #    handed the caller's set, not a shared one.
    HIS_ROOTS = {"CAD": settings.collab_cad, "Photos": settings.collab_photos}
    HER_COLLAB = Path(os.path.expanduser("~/Jeanne/Collab"))
    HER_ROOTS = {"Projects": HER_COLLAB / "Projects", "Files": HER_COLLAB / "Files"}
    HIS_INBOX = settings.inbox
    HER_INBOX = HER_COLLAB / "Files"

    def _roots_for(user: str | None) -> dict[str, Path]:
        return HER_ROOTS if (user or "").strip().lower() == "jeanne" else HIS_ROOTS

    def _inbox_for(user: str | None) -> Path:
        return HER_INBOX if (user or "").strip().lower() == "jeanne" else HIS_INBOX

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
    async def list_files(
        path: str = Query("", max_length=1024),
        user: str | None = Query(None, max_length=64),
    ) -> dict[str, Any]:
        """One directory. An empty `path` lists the roots themselves."""
        try:
            return await run_in_threadpool(files_mod.listdir, path, _roots_for(user))
        except files_mod.BrowseError as exc:
            raise _browse_error(exc) from exc

    @app.get(
        "/files/raw", tags=["files"], dependencies=[Depends(require_auth_flex)]
    )
    async def raw_file(
        path: str = Query(..., max_length=1024),
        user: str | None = Query(None, max_length=64),
    ) -> FileResponse:
        """The file itself -- the `<img>` target, the STL the viewer loads."""
        try:
            target = await run_in_threadpool(
                files_mod.resolve_file, path, _roots_for(user))
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
        user: str | None = Query(None, max_length=64),
    ) -> FileResponse:
        """A small JPEG for the grid, falling back to the original.

        A 2 MB phone photo per tile is a real cost over a tailnet link to a
        Pixel 1, so this shells out to `sips` and caches. If that is not
        available the page still works -- it is just heavier.
        """
        try:
            target = await run_in_threadpool(
                files_mod.resolve_file, path, _roots_for(user))
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
    async def upload_file(
        file: UploadFile = File(...),
        user: str | None = Query(None, max_length=64),
    ) -> dict[str, Any]:
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
                files_mod.deposit, file.filename or "attachment", data,
                _inbox_for(user)
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
                files_mod.share, payload.path,
                _roots_for(payload.user), _inbox_for(payload.user)
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
    async def stl_page(
        path: str = Query(..., max_length=1024),
        user: str | None = Query(None, max_length=64),
    ) -> HTMLResponse:
        """The STL viewer. ⚠️ **STL only** -- see `web/stl.html` for why.

        The path is resolved before the page is served, so a bad one is a 404
        here rather than a viewer that loads, spins and fails.
        """
        try:
            target = await run_in_threadpool(
                files_mod.resolve_file, path, _roots_for(user))
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

    # -------------------------------------------------------- cron / schedules

    def _cron_fields(payload: CronJobRequest) -> dict[str, Any]:
        """Validate a job's schedule and return the row fields to store. A bad
        expr/tz raises here as a 400 rather than failing silently at fire time."""
        kind = (payload.kind or "").lower()
        if kind not in ("at", "every", "cron"):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="kind must be 'at', 'every' or 'cron'",
            )
        try:
            next_run = cron_mod.first_run(
                kind, payload.expr, payload.tz or "", time.time()
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return {
            "name": payload.name or "",
            "kind": kind,
            "expr": payload.expr,
            "tz": payload.tz or "",
            "pane_id": normalise_pane_id(payload.pane_id) if payload.pane_id else "",
            "prompt": payload.prompt or "",
            "delivery": payload.delivery or "channel",
            "owner": payload.owner or apps_mod.DEFAULT_USER,
            "enabled": payload.enabled,
            "delete_after_run": payload.delete_after_run,
            "next_run_at": next_run,
        }

    @app.get("/cron", tags=["cron"], dependencies=[Depends(require_auth_flex)])
    async def list_cron() -> dict[str, Any]:
        st = _store()
        jobs = await run_in_threadpool(st.list_jobs, None)
        for j in jobs:
            j["schedule"] = cron_mod.describe(j)
        return {"jobs": jobs}

    @app.post(
        "/cron", tags=["cron"], dependencies=[Depends(require_auth)],
        status_code=status.HTTP_201_CREATED,
    )
    async def create_cron(payload: CronJobRequest) -> dict[str, Any]:
        job = await run_in_threadpool(_store().create_job, _cron_fields(payload))
        job["schedule"] = cron_mod.describe(job)
        app.state.broadcaster.publish({"type": "cron", "action": "created", "job": job})
        return job

    @app.get(
        "/cron/{job_id}", tags=["cron"],
        dependencies=[Depends(require_auth_flex)],
    )
    async def get_cron(job_id: int = PathParam(...)) -> dict[str, Any]:
        st = _store()
        job = await run_in_threadpool(st.get_job, job_id)
        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no such job")
        job["schedule"] = cron_mod.describe(job)
        job["runs"] = await run_in_threadpool(st.list_runs, job_id, 20)
        return job

    @app.patch("/cron/{job_id}", tags=["cron"], dependencies=[Depends(require_auth)])
    async def patch_cron(
        payload: CronPatchRequest, job_id: int = PathParam(...)
    ) -> dict[str, Any]:
        st = _store()
        existing = await run_in_threadpool(st.get_job, job_id)
        if existing is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no such job")
        fields = payload.model_dump(exclude_none=True)
        if fields.get("pane_id"):
            fields["pane_id"] = normalise_pane_id(fields["pane_id"])
        # Recompute the next fire when the schedule (or enabled) changed, so an
        # edit takes effect immediately instead of on the old cadence.
        if any(k in fields for k in ("kind", "expr", "tz", "enabled")):
            merged = {**existing, **fields}
            try:
                fields["next_run_at"] = cron_mod.first_run(
                    merged["kind"], merged["expr"], merged.get("tz") or "", time.time()
                )
            except ValueError as exc:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, detail=str(exc)
                ) from exc
        job = await run_in_threadpool(st.update_job, job_id, fields)
        job["schedule"] = cron_mod.describe(job)
        app.state.broadcaster.publish({"type": "cron", "action": "updated", "job": job})
        return job

    @app.delete("/cron/{job_id}", tags=["cron"], dependencies=[Depends(require_auth)])
    async def delete_cron(job_id: int = PathParam(...)) -> dict[str, Any]:
        ok = await run_in_threadpool(_store().delete_job, job_id)
        if not ok:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no such job")
        app.state.broadcaster.publish({"type": "cron", "action": "deleted", "id": job_id})
        return {"deleted": job_id}

    @app.post("/cron/{job_id}/run", tags=["cron"], dependencies=[Depends(require_auth)])
    async def run_cron(job_id: int = PathParam(...)) -> dict[str, Any]:
        """Fire a job right now WITHOUT disturbing its schedule (manual test)."""
        job = await run_in_threadpool(_store().get_job, job_id)
        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no such job")
        ok, detail = await cron_mod.deliver(app, job)
        return {"fired": ok, "detail": detail, "job_id": job_id}

    @app.get(
        "/schedules", tags=["cron"],
        dependencies=[Depends(require_auth_flex)],
        response_class=HTMLResponse,
    )
    async def schedules_page() -> HTMLResponse:
        """The Schedules app -- a hub-served page. See `web/schedules.html`."""
        return _page("schedules.html", {'"__ROAM_TOKEN__"': _js_literal(token)})

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

    @app.get("/streams", tags=["stream"],
             dependencies=[Depends(require_auth_flex)])
    async def list_streams() -> dict[str, Any]:
        """Every live stream, for the picker.

        ★ A stream exists because somebody is in it and stops existing when the last
        member leaves. There is no create/delete to get out of step with reality, and
        the list can never offer a room nobody is in.

        ⚠️ So "+ new stream" on a client is not a call to this API — it is joining a
        name that does not exist yet. Creating one and then failing to join it would
        be the only way to produce an empty stream, so there is no such call.
        """
        streams: intercom_mod.Streams = app.state.streams
        return {"streams": streams.snapshot(), "devices": streams.roster()}

    @app.post("/streams/{name}/end", tags=["stream"],
              dependencies=[Depends(require_auth_flex)])
    async def end_stream(name: str = PathParam(..., max_length=32)) -> dict[str, Any]:
        """Close a stream, from anywhere.

        ★★ Deliberately REST and deliberately not scoped to a member. Ending used to
        require being in the stream, which meant the one moment you most need to shut
        a camera off — you are looking at a list and something is live that should not
        be — was the moment you could not. Owner: *"just click the X on the stream to
        close it ... my laptop cam is still on right now because i didn't know how to
        close it."*

        ⚠️ Every member is TOLD to leave rather than merely forgotten: only a device
        can close its own lens, so clearing hub state alone would leave a camera
        running with nobody watching.
        """
        streams: intercom_mod.Streams = app.state.streams
        try:
            key = intercom_mod.Streams.normalise(name)
        except intercom_mod.IntercomError as exc:
            raise HTTPException(400, detail=str(exc)) from exc
        live = streams.find(key)
        if live is None:
            raise HTTPException(404, detail=f"no such stream: {key}")

        peers = app.state.intercom_peers
        members = live.end()
        for member in members:
            sock = peers.get((key, member))
            if sock is None:
                continue
            with contextlib.suppress(Exception):
                await sock.send_json({
                    "type": "drive", "by": "hub", "stream": key,
                    "action": "leave", "value": None,
                })
        streams.prune()
        return {"ended": key, "members": members}

    @app.get("/intercom/state", tags=["channels"],
             dependencies=[Depends(require_auth_flex)])
    async def intercom_state() -> dict[str, Any]:
        """Who holds the floor, and how many audio frames each device sent/received.

        ★ Exists to answer one question without a second round of guessing: when
        talk-back does not arrive, is the talker not capturing, is the hub not
        relaying, or is the listener not playing? rx_frames on the talker and
        tx_frames on the sender separate all three.
        """
        streams: intercom_mod.Streams = app.state.streams
        # ★ The default stream is still spread at the top level so existing tooling
        #   and the diagnostics above keep reading the same keys; `streams` carries
        #   the full picture now that there can be more than one.
        ic = streams.get(intercom_mod.DEFAULT_STREAM)
        return {
            **ic.snapshot(),
            "streams": streams.snapshot(),
            "peers": sorted(f"{s}/{d}" for s, d in app.state.intercom_peers),
            "stats": app.state.intercom_stats,
            "queued": {k: len(v) for k, v in app.state.queued.items()},
        }

    @app.websocket("/intercom/video")
    async def intercom_video(
        websocket: WebSocket,
        device: str = Query(..., min_length=1, max_length=64),
        stream: str | None = Query(default=None, max_length=32),
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
        streams: intercom_mod.Streams = app.state.streams
        try:
            stream_name = intercom_mod.Streams.normalise(stream)
        except intercom_mod.IntercomError as exc:
            await websocket.send_json({"type": "error", "detail": str(exc)})
            await websocket.close(code=4400)
            return
        ic = streams.get(stream_name)
        peers: dict[tuple[str, str], WebSocket] = app.state.video_peers
        key = (stream_name, device)
        peers[key] = websocket
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
                    # Same rule as audio: a picture never crosses streams.
                    if other[0] != stream_name or other[1] == device:
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
        # "source" | "monitor" | "standby" (the old "sender"/"receiver" still work).
        # Standby holds the socket and takes no part -- see `Intercom.set_standby`.
        role: str = Query(default="monitor"),
        # Which stream. Absent means the default one, so a client that predates
        # named streams keeps working untouched.
        stream: str | None = Query(default=None, max_length=32),
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
        streams: intercom_mod.Streams = app.state.streams
        try:
            stream_name = intercom_mod.Streams.normalise(stream)
        except intercom_mod.IntercomError as exc:
            await websocket.send_json({"type": "error", "detail": str(exc)})
            await websocket.close(code=4400)
            return
        ic = streams.get(stream_name)
        peers: dict[tuple[str, str], WebSocket] = app.state.intercom_peers
        key = (stream_name, device)
        # ⚠️⚠️ ONE SOCKET PER DEVICE PER STREAM, and the old one is CLOSED rather than
        #    merely dropped. A client that reconnects while its previous socket is
        #    still open -- an app resuming from doze does this constantly -- left two
        #    live sockets under one key. Whichever closed first then ran the cleanup
        #    and evicted the survivor, so the device disappeared from the roster while
        #    plainly still connected. Closing the loser makes "registered" and
        #    "connected" the same thing again.
        if (stale := peers.get(key)) is not None and stale is not websocket:
            with contextlib.suppress(Exception):
                await stale.close(code=1012)
        peers[key] = websocket

        async def announce() -> None:
            """Tell THIS stream's members where the floor is.

            ⚠️ Scoped to the stream. Broadcasting every floor to every socket would
            make one room's talk-back look like an interruption in another.
            """
            snap = {"type": "floor", **ic.snapshot()}
            for other, sock in list(peers.items()):
                if other[0] != stream_name:
                    continue
                try:
                    await sock.send_json(snap)
                except (WebSocketDisconnect, RuntimeError):
                    peers.pop(other, None)

        # ⚠️ Standby is presence, NOT membership. Registering it against the stream
        #    is what conjured a room out of a merely-reachable laptop.
        streams.arrive(device, None if role == "standby" else stream_name)
        if role in ("source", "sender"):
            ic.open_channel(device)
        elif role == "standby":
            # ★★ Connected, but taking no part. This is how a device stays reachable
            #    for a remote start while Stream reads as OFF -- "off" has to mean
            #    silent, not absent, or nothing can ever wake it.
            ic.set_standby(device, True)
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
                    # ⚠️ The gate is the floor, plus mute FOR A SOURCE ONLY. Mute is
                    #    a source concept; a monitor's mic is governed by the floor
                    #    alone. Applying it to everyone left every monitor muted with
                    #    no control to open it, and PTT went silent.
                    if ic.holder() != device or (
                        device == ic.sender and ic.is_muted(device)
                    ):
                        st["dropped_no_floor"] += 1
                        continue
                    if device == ic.sender:
                        ic.touch_sender()
                    targets: list[tuple[tuple[str, str], WebSocket]] = []
                    for other, sock in list(peers.items()):
                        # ⚠️⚠️ SAME STREAM ONLY. This is the line that makes "talk to
                        #    my wife without disrupting my son" true; without it the
                        #    audio of every stream lands in every other one.
                        if other[0] != stream_name or other[1] == device:
                            continue
                        # ⚠️ A standby device is a doorbell, not an ear. Sending it
                        #    audio would burn the link on frames nothing plays, and
                        #    on a phone that is somebody's battery.
                        if ic.is_standby(other[1]):
                            continue
                        targets.append((other, sock))

                    # ⚠️⚠️ CONCURRENTLY, and with a deadline each. Awaiting peers one
                    #    at a time means the slowest socket in the room sets the
                    #    latency for everybody behind it in the loop -- one phone on
                    #    a bad link and the whole house hears late. Harmless with two
                    #    devices; with several streams and several members each it is
                    #    the thing that would make this feel broken.
                    #
                    # ★ A frame is 640 bytes of 20ms audio. If a peer cannot take it
                    #   within a frame time, the frame is already stale and DROPPING
                    #   it is correct -- late audio is worse than missing audio, and
                    #   buffering it just moves the delay further out.
                    async def _relay(entry, frame=raw):
                        who, sock = entry
                        try:
                            await asyncio.wait_for(
                                sock.send_bytes(frame), timeout=RELAY_DEADLINE_S
                            )
                        except (WebSocketDisconnect, RuntimeError):
                            peers.pop(who, None)
                            return
                        except (asyncio.TimeoutError, asyncio.CancelledError):
                            st = app.state.intercom_stats.setdefault(
                                who[1], {"rx_frames": 0, "rx_bytes": 0, "tx_frames": 0,
                                         "tx_bytes": 0, "dropped_no_floor": 0})
                            st["dropped_slow"] = st.get("dropped_slow", 0) + 1
                            return
                        ost = app.state.intercom_stats.setdefault(
                            who[1], {"rx_frames": 0, "rx_bytes": 0, "tx_frames": 0,
                                     "tx_bytes": 0, "dropped_no_floor": 0}
                        )
                        ost["tx_frames"] += 1
                        ost["tx_bytes"] += len(frame)

                    if targets:
                        await asyncio.gather(*(_relay(t) for t in targets))
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
                    elif kind == "mute":
                        # This device opening or closing its OWN microphone. Like
                        # `allow_remote`, there is no form of this that acts on
                        # somebody else's mic -- muting a person remotely is a
                        # different feature with different consent.
                        ic.set_muted(device, bool(control.get("on", True)))
                    elif kind == "allow_remote":
                        # This device consenting for ITSELF. There is no form of
                        # this message that grants it on another device's behalf.
                        ic.allow_remote(device, bool(control.get("on", True)))
                        streams.set_armed(device, bool(control.get("on", True)))
                    elif kind == "end":
                        # ★★ Close the stream for EVERYONE, and turn their cameras and
                        #    microphones off on the way out. Owner: *"I can't just
                        #    close a stream ... that should automatically turn the
                        #    camera and mic back off on the sender device."*
                        #
                        # ⚠️ Each member is told to leave rather than merely being
                        #    forgotten: only a device can close its own lens, so a hub
                        #    that just cleared its own state would leave a camera
                        #    running with nobody watching -- the exact outcome this
                        #    exists to prevent.
                        for member in ic.end():
                            if member == device:
                                continue
                            other = peers.get((stream_name, member))
                            if other is None:
                                continue
                            with contextlib.suppress(Exception):
                                await other.send_json({
                                    "type": "drive", "by": device,
                                    "stream": stream_name,
                                    "action": "leave", "value": None,
                                })
                        streams.prune()
                    elif kind == "drive":
                        # ★★ REMOTE CONTROL, which is the product. Owner: *"i should
                        #    be able to ... set the mac as sender, myself as receiver
                        #    and make sure the mic and camera are toggle-able from my
                        #    pixel11."* Walking to the other machine to configure it
                        #    defeats the entire purpose of an intercom.
                        #
                        # ⚠️ Gated on the TARGET having armed itself. Arming is the
                        #    one consent, and it covers being made a source, having a
                        #    microphone opened and having a camera switched on --
                        #    they are the same act from the far side: somebody else
                        #    turning your machine into a live device in your room.
                        target = str(control.get("target") or "")
                        if not target or target == device:
                            continue
                        if not streams.is_armed(target):
                            raise intercom_mod.IntercomError(
                                f"{target} has not enabled remote control"
                            )
                        sock = None
                        for (sname, dname), candidate in peers.items():
                            if dname == target:
                                sock = candidate
                                break
                        if sock is None:
                            raise intercom_mod.IntercomError(
                                f"{target} is not connected"
                            )
                        # ⚠️ A DIRECTIVE, not a state change. Only the target can open
                        #    its own microphone or camera; the hub declaring it done
                        #    would produce a device that reads as live and delivers
                        #    silence -- the failure this system keeps re-learning.
                        # ⚠️⚠️ CARRIES THE WHOLE SETUP. Making a device a Source makes
                        #    it RECONNECT -- the stream is a query parameter on its
                        #    socket -- so a follow-up "camera" or "mute" sent a
                        #    moment later lands on a socket that is already closing
                        #    and is simply lost. Owner: *"i pick the mac as sender and
                        #    set the mic and camera how i want it but it doesn't do
                        #    anything."* One directive, applied by the target AFTER it
                        #    has joined, has no such window.
                        directive = {
                            "type": "drive",
                            "by": device,
                            "stream": stream_name,
                            "action": str(control.get("action") or ""),
                            "value": control.get("value"),
                            "camera": control.get("camera"),
                            "mute": control.get("mute"),
                        }
                        try:
                            await sock.send_json(directive)
                        except (WebSocketDisconnect, RuntimeError) as exc:
                            raise intercom_mod.IntercomError(
                                f"{target} went away"
                            ) from exc
                    elif kind == "open":
                        target = str(control.get("target") or device)
                        if target == device:
                            ic.open_channel(device)
                        else:
                            # ★★ A DIRECTIVE, not a state change. Only the target can
                            #    open its own microphone -- see `request_open`. If the
                            #    hub flipped the floor here, a target that was asleep
                            #    or had mic permission denied would leave a channel
                            #    that reads as open and carries no audio.
                            ic.request_open(target, by=device)
                            sock = peers.get((stream_name, target))
                            if sock is None:
                                raise intercom_mod.IntercomError(
                                    f"{target} is not connected"
                                )
                            try:
                                await sock.send_json(
                                    {"type": "become_sender", "by": device}
                                )
                            except (WebSocketDisconnect, RuntimeError) as exc:
                                peers.pop((stream_name, target), None)
                                raise intercom_mod.IntercomError(
                                    f"{target} went away"
                                ) from exc
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
            # ⚠️⚠️ ONLY clean up if this socket is still the one registered for this
            #    device. Cleanup used to be keyed on the NAME alone, and a device
            #    that reconnects — which happens on every single role change, since
            #    the client tears the socket down and immediately opens another —
            #    would have its NEW connection destroyed by its OLD one's teardown
            #    arriving late.
            #
            #    That one race produced every symptom he reported at once: the Mac
            #    vanished from `standby` while its app was plainly running, so the
            #    hub could no longer reach it; and because the fresh socket had
            #    already been handed a snapshot still carrying `video`, the Mac
            #    restarted its camera and then never heard the message turning it
            #    off — *"when i turn off the stream, the video stream stays running
            #    on the mac"*, with a green light on and nothing able to stop it.
            if peers.get(key) is websocket:
                peers.pop(key, None)
                # Only forget the device if it has no other socket anywhere.
                if not any(d == device for _, d in peers):
                    streams.depart(device)
                if ic.sender == device:
                    ic.close_channel(device)
                else:
                    ic.leave(device)
                await announce()
                # An empty stream stops existing, so the picker never offers a room
                # nobody is in.
                streams.prune()

    @app.websocket("/ws")
    async def websocket_endpoint(
        websocket: WebSocket,
        since: int | None = Query(default=None, ge=0),
        # ★★ WHOSE rail this socket is. The channel LIST is filtered by it, on the
        #    hub, per socket — because the list arrives over THIS socket (the `hello`
        #    and `channels` frames), not over the REST route that already filtered.
        #    A second person joined and saw every channel: the filter was only ever on
        #    the road nobody drove.
        user: str | None = Query(default=None, max_length=64),
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
                    "channels": [
                        r for r in build_channel_list(st, live, asking_panes=set(app.state.prompts))
                        if _visible_to(r, user)
                    ],
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
                    # ⚠️ A `channels` frame is BROADCAST identically to every socket,
                    #    so it must be narrowed to this socket's user before it goes
                    #    out — otherwise the poller quietly hands her his whole rail a
                    #    couple of seconds after `hello` correctly withheld it.
                    if message.get("type") == "channels":
                        message = {
                            **message,
                            "channels": [
                                r for r in message.get("channels", [])
                                if _visible_to(r, user)
                            ],
                        }
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


def _visible_to(view: dict[str, Any], user: str | None) -> bool:
    """Whether a built channel row belongs on `user`'s list.

    Mirrors `Channel.visible_to`, but works off the merged view so it covers DEAD
    channels too -- their pane is gone and its options with it, so the owner comes
    from the store.
    """
    # ⚠️ The @host dead-letter channel is a box-side monitor, not something either
    #    person converses with -- owner: *"i don't need that shit ... keep it for YOU
    #    to monitor, and if shit does go there, that's a bug we should fix."* Hidden
    #    from every user's list; it still exists and still catches stray pane-less
    #    notices, which the box side watches.
    if view.get("pane_id") == HOST_CHANNEL_ID:
        return False
    owner = (view.get("owner") or "").strip().lower()
    name = (user or channels_mod.DEFAULT_OWNER).strip().lower()
    if owner == channels_mod.SHARED:
        return True
    if not owner:
        return name == channels_mod.DEFAULT_OWNER
    return owner == name


def _remember_all(store: Store, live: list[Channel]) -> None:
    for ch in live:
        store.remember_channel(ch.pane_id, ch.label, ch.session, owner=ch.owner)


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
        # ★ Prompt detection rides the SAME capture as the liveness hash -- no extra
        #   tmux calls, just a cheap parse of ~60 lines. It MUST see every screen, not
        #   only the ones that moved this poll. A selector that is already up when this
        #   process starts (every deploy resets `digests` and `app.state.prompts`) or
        #   after a transient parse-miss cleared it sits perfectly static -- its digest
        #   never changes again, so gating detection on movement lost it forever:
        #   Warble sat on an open question for a WEEK, unanswerable from the app and
        #   showing "idle". Re-parsing a stable selector is idempotent (events fire only
        #   on a fingerprint change), so this costs nothing but correctness.
        screens[ch.pane_id] = content
        # A pane we have never sampled counts as active now: it is the best
        # reading available, and claiming "idle for hours" would be a lie.
        if previous is None or previous != digest:
            store.set_channel_activity(ch.pane_id, now)
            moved[ch.pane_id] = now
    for pane_id in set(digests) - {c.pane_id for c in live}:
        digests.pop(pane_id, None)
    return moved


async def _flush_when_idle(app: FastAPI, pane_id: str, budget_s: float = 300.0) -> None:
    """Deliver a held message once the pane stops replying.

    Unlike the prompt flush, a reply can run for minutes, so poll `busy()` until the
    interrupt hint clears (or a budget elapses), then hand off through the same
    settled gate. One message per idle window: sending two in a burst would drop the
    second into the reply the first just triggered, so any remainder re-schedules
    itself after this reply.
    """
    store: Store = app.state.store
    broadcaster: Broadcaster = app.state.broadcaster
    deadline = time.monotonic() + budget_s
    while time.monotonic() < deadline:
        # ★★ A selector that opened WHILE we waited must stop this flush dead.
        #    `_flush_idle_queues` has always skipped panes with an open prompt;
        #    this per-send waiter did not, so a message held for a reply could be
        #    typed straight into a question that appeared in the meantime -- the
        #    text lands in the menu and the Enter dismisses it ("User declined to
        #    answer questions"), losing both the answer and the message. Bail and
        #    leave it queued: /respond flushes it once the question is answered.
        if pane_id in app.state.prompts:
            return
        if not await run_in_threadpool(channels_mod.busy, pane_id):
            break
        await asyncio.sleep(1.0)
    else:
        return  # still busy after the budget; a later send re-triggers the flush
    if not await run_in_threadpool(channels_mod.settled, pane_id):
        return
    if pane_id in app.state.prompts:   # opened during the settle window
        return
    held = app.state.queued.get(pane_id, [])
    if not held:
        return
    text = held.pop(0)
    try:
        await run_in_threadpool(channels_mod.send, pane_id, text, True)
    except (TmuxError, ValueError) as exc:
        held.insert(0, text)
        event = store.append(
            pane_id, EventKind.ERROR,
            f"held message could not be sent: {exc}", meta={"attempted": text},
        )
        broadcaster.publish({"type": "event", "event": event.to_dict()})
        return
    if app.state.queued.get(pane_id):        # more waiting -> after this reply
        asyncio.create_task(_flush_when_idle(app, pane_id))


async def _flush_idle_queues(app: FastAPI) -> None:
    """Deliver messages held while a channel was mid-reply, from the poll loop.

    ⚠️ Why here and not a per-send task: a per-send waiter that gives up after a
    budget STRANDS the message -- one sat queued 14.5 h, then a later send flushed
    it wildly out of context. The poller runs every cycle, so a held message lands
    the moment its channel goes idle. One per cycle per pane (serialise, so the
    next does not drop into the reply this one triggers). Panes with an open prompt
    are skipped -- those flush via /respond once the selector is answered.
    """
    store: Store = app.state.store
    broadcaster: Broadcaster = app.state.broadcaster
    for pane_id, queued in list(app.state.queued.items()):
        if not queued or pane_id in app.state.prompts:
            continue
        try:
            if await run_in_threadpool(channels_mod.busy, pane_id):
                continue
            if not await run_in_threadpool(channels_mod.settled, pane_id):
                continue
            # ⚠️ Never type a held message into a live selector -- re-parse the
            #    screen right before sending, so a held message can't answer or
            #    dismiss an open dialog even if the prompt state lags.
            if prompts_mod.parse(
                await run_in_threadpool(channels_mod.screen, pane_id)
            ) is not None:
                continue
        except TmuxError:
            continue
        text = queued.pop(0)
        try:
            await run_in_threadpool(channels_mod.send, pane_id, text, True)
        except (TmuxError, ValueError) as exc:
            queued.insert(0, text)
            event = store.append(
                pane_id, EventKind.ERROR,
                f"held message could not be sent: {exc}", meta={"attempted": text},
            )
            broadcaster.publish({"type": "event", "event": event.to_dict()})


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


#: Consecutive polls a selector must be absent before its prompt is cleared. A
#: single miss is a transient redraw (a status line over the menu), not an answer;
#: clearing on one closed live dialogs out from under the wearer.
PROMPT_CLEAR_MISSES = 3


def _watch_prompts(
    app: FastAPI,
    store: Store,
    broadcaster: Broadcaster,
    screens: dict[str, str],
    open_prompts: dict[str, str],
    prompt_misses: dict[str, int],
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
                # ⚠️ Debounce: a single failed parse -- a status line redrawing over
                #    the selector, a transient scroll -- must not dismiss a live
                #    prompt. Clear only after it is gone for several polls in a row.
                #    This is the bug where a stray status frame closed an open dialog.
                misses = prompt_misses.get(pane_id, 0) + 1
                prompt_misses[pane_id] = misses
                if misses >= PROMPT_CLEAR_MISSES:
                    open_prompts.pop(pane_id, None)
                    prompts_state.pop(pane_id, None)
                    prompt_misses.pop(pane_id, None)
                    broadcaster.publish(
                        {"type": "prompt", "pane": pane_id, "prompt": None}
                    )
            continue
        prompt_misses.pop(pane_id, None)  # selector present -> reset the miss count

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
    prompt_misses: dict[str, int] = {}  # pane_id -> consecutive polls the selector was gone
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
                _watch_prompts(app, store, broadcaster, screens, open_prompts, prompt_misses)
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
                        "channels": build_channel_list(store, live, asking_panes=set(app.state.prompts)),
                        "server_time": time.time(),
                    }
                )
            known = current
            await _flush_idle_queues(app)   # deliver held messages once idle
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
