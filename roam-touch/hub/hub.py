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
import logging
import os
import re
import secrets
import stat
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Iterator

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Path as PathParam,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import AliasChoices, BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.concurrency import run_in_threadpool

import channels as channels_mod
from channels import Channel, TmuxError
from store import DEFAULT_DB_PATH, EventKind, Store, StoredChannel

HUB_DIR = Path(__file__).resolve().parent
HUB_VERSION = "1.0.0"
PROTOCOL_VERSION = 1

#: WebSocket frames a subscriber may fall behind by before we cut it loose and
#: make it reconnect with `?since=` (which replays from the store, losslessly).
SUBSCRIBER_QUEUE_MAX = 512
#: Seconds of silence before the hub sends an application-level ping frame.
HEARTBEAT_SECONDS = 30.0

_PANE_RE = re.compile(r"^%\d+$")

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
    capture_lines: int = 200
    history_limit: int = 200
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
    """
    pane_id = raw.strip()
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


class ArchiveRequest(BaseModel):
    archived: bool = True


# --------------------------------------------------------------------- views


def channel_status(live: bool, last_kind: str | None) -> str:
    """`dead` | `working` | `idle` -- what the panel puts on the channel chip."""
    if not live:
        return "dead"
    if last_kind in (EventKind.SENT.value, EventKind.RECEIPT.value):
        return "working"
    return "idle"


def channel_view(
    store: Store,
    pane_id: str,
    live: Channel | None,
    stored: StoredChannel | None,
) -> dict[str, Any]:
    """One merged channel: whatever tmux says now, plus whatever we remember."""
    last = store.last_event(pane_id)
    label = live.label if live else (stored.label if stored else pane_id)
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
        "event_count": store.event_count(pane_id),
        "last_event": last.to_dict() if last else None,
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

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.store = store or Store(settings.db_path)
        app.state.broadcaster = Broadcaster()
        app.state.settings = settings
        app.state.token = token
        app.state.started_at = time.time()
        app.state.tmux_ok = True
        app.state.live_channels = []
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

    def _publish_event(event) -> None:
        _publish({"type": "event", "event": event.to_dict()})

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
            "subscribers": app.state.broadcaster.subscriber_count,
            "db_path": str(st.path),
        }

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
        "/channels/{pane}/send",
        tags=["channels"],
        dependencies=[Depends(require_auth)],
    )
    async def send_endpoint(payload: SendRequest, pane: str = PathParam(...)):
        pane_id = normalise_pane_id(pane)
        st = _store()
        live = await run_in_threadpool(channels_mod.get, pane_id)
        if live is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"channel {pane_id} is not live; nothing was sent",
            )
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
            "events": [e.to_dict() for e in events],
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
        event = st.append(pane_id, payload.kind, payload.body, payload.meta)
        _publish_event(event)
        return {"event": event.to_dict()}

    @app.get("/events", tags=["events"], dependencies=[Depends(require_auth)])
    async def get_events(
        since: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=2000)
    ) -> dict[str, Any]:
        """Everything after `since`, across all channels -- WebSocket catch-up
        for clients that would rather poll once on wake than hold a socket."""
        st = _store()
        events = st.events_since(since, limit)
        return {
            "events": [e.to_dict() for e in events],
            "latest_event_id": st.latest_event_id(),
        }

    # ----------------------------------------------------------- websocket

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
                }
            )
            if since is not None:
                backlog = st.events_since(since)
                await websocket.send_json(
                    {
                        "type": "backlog",
                        "since": since,
                        "events": [e.to_dict() for e in backlog],
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
    known: dict[str, str] | None = None  # pane_id -> label
    while True:
        try:
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
