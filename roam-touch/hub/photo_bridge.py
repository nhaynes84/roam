#!/usr/bin/env python3
"""ROAM photo bridge -- a Google Photos shared album as Claude's inbox.

The contract is the album, not the code: he makes one shared album, drops its
public link in `photo-album.txt`, and from then on **anything he adds to that
album is something he wants Claude to see**. No per-photo decision, no upload
step, no account anywhere near this box. Take the picture on the phone, add it
to the album, and it turns up in `~/.claude/dropzone/inbox/`.

★ **Not the Google Photos Library API.** Google revoked the library-read scopes
in March 2025; an OAuth app can only see media *it itself created*, so it can
never read his album. The public share page is the supported path and it needs
no credentials at all -- which is the point, because this machine signs into
nothing. Do not "fix" this back to the API.

How the page is read: a shared album is server-rendered, and the item list is
sitting in the initial HTML inside `AF_initDataCallback({... data:[...] ...})`
-- Google's own hydration payload. Plain HTTP plus a bracket-matching scan of
that block gets the media base URLs with no browser, no JS engine and no
headless Chrome to keep alive on a machine that is also a workstation.

⚠️ **The `photos.app.goo.gl` short link must not be followed with a browser
User-Agent.** It is a Firebase Dynamic Links interstitial: to a desktop UA it
answers **200 with a JavaScript shell that does not contain the destination
anywhere in its HTML**, so a plain redirect-following GET lands nowhere and
parses to zero items. A HEAD that does *not* follow redirects answers a clean
302 whose `Location` is the real `photos.google.com/share/...` URL. Verified
2026-08-14 by hand with curl; `resolve_share_url` is that request.

⚠️ **Privacy:** these files arrive with their EXIF intact -- including **GPS
coordinates and the source device model** -- and land somewhere Claude reads.
Nothing here strips it, on purpose: that is the owner's call to make, not a
silent default. Worth knowing before pointing this at a camera roll.

Everything else is defensive, because this runs on a timer and must never be
the reason a prompt is slow or a launchd job is red:

* No album file, or an empty one -> exit 0, silently. He has not made it yet.
* Any network or parse failure -> logged, exit 0. Next run tries again.
* **First run only records the high-water mark.** An album with 800 holiday
  photos in it must not land 800 files in the inbox the first time this runs.
  New means "added since the bridge last looked", forever after.

Run:  ./.venv/bin/python photo_bridge.py            (single shot; launchd repeats)
      ./.venv/bin/python photo_bridge.py --verbose  (also log to stderr)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterator

HUB_DIR = Path(__file__).resolve().parent
BRIDGE_VERSION = "1.0.0"

log = logging.getLogger("roam.photos")


def _env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name, "").strip()
    return Path(raw).expanduser() if raw else default


#: The public share link, one per line, `#` comments allowed. Gitignored: it is
#: a capability URL -- anyone holding it can read the album.
CONFIG_PATH = _env_path("ROAM_PHOTOS_ALBUM_FILE", HUB_DIR / "photo-album.txt")
#: The high-water mark. Media ids already seen, plus the newest timestamp.
STATE_PATH = _env_path("ROAM_PHOTOS_STATE", HUB_DIR / "photo-state.json")
#: Where new files land. The `clip-fetch` prompt hook is what makes them
#: visible to Claude -- a file sitting in a directory is not context.
INBOX = _env_path("ROAM_PHOTOS_INBOX", Path.home() / ".claude" / "dropzone" / "inbox")
LOG_PATH = _env_path("ROAM_PHOTOS_LOG", Path.home() / "Library" / "Logs" / "roam-photos.log")

#: Chrome's UA. The share page serves a different, JS-only shell to clients it
#: does not recognise, and then there is no `AF_initDataCallback` to read.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
#: ⚠️ Deliberately NOT a browser. The dynamic-link shortener answers a browser
#: with a 200 JS interstitial that hides the destination; a plain client gets
#: the 302. See the module docstring.
SHORTLINK_UA = "curl/8.7.1"
#: Hosts that are a redirect to the album rather than the album.
SHORTLINK_HOSTS = ("photos.app.goo.gl", "goo.gl")
PAGE_TIMEOUT_S = 20.0
DOWNLOAD_TIMEOUT_S = 120.0
#: One run is a catch-up, not a migration. The rest arrive on the next tick.
MAX_ITEMS_PER_RUN = 25
#: A photo that is not a photo. 512 MiB is generous for a phone video.
MAX_BYTES = 512 * 1024 * 1024
#: How many ids to remember. Well past `MAX_ITEMS_PER_RUN * runs-per-day`.
SEEN_LIMIT = 5000

#: Google serves media from `lh3.googleusercontent.com` and friends. `/pw/` is
#: the shared-album form; avatars and UI chrome live on other paths and are
#: excluded by the structural match below, not by this.
_MEDIA_HOST_RE = re.compile(r"^https://[\w.-]*\.(?:googleusercontent\.com|ggpht\.com)/", re.I)
#: A trailing option string on a base URL (`=w530-h354-n`). Replaced with `=d`.
_URL_OPTIONS_RE = re.compile(r"=[\w-]*$")
_AF_CALL_RE = re.compile(r"AF_initDataCallback\s*\(")
_DATA_KEY_RE = re.compile(r"[\{,]\s*data\s*:\s*")
_UNSAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


class MediaItem:
    """One photo or video in the album, as the share page describes it."""

    __slots__ = ("id", "url", "ts_ms")

    def __init__(self, id: str, url: str, ts_ms: int | None = None) -> None:
        self.id = id
        self.url = url
        self.ts_ms = ts_ms

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"MediaItem(id={self.id!r}, ts_ms={self.ts_ms!r})"

    @property
    def download_url(self) -> str:
        """The original file. `=d` on a base URL is the full-resolution one.

        Without it Google serves whatever downscaled derivative the page was
        using -- a 530px preview of a CAD render is worse than useless.
        """
        return _URL_OPTIONS_RE.sub("", self.url) + "=d"


# ------------------------------------------------------------------- config


def read_album_url(path: Path = CONFIG_PATH) -> str | None:
    """The share link, or None when he has not set one up yet.

    Missing file, empty file, comments only -> None, and the caller exits 0.
    That is the steady state until he creates the album, and it must be quiet.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("http://") or line.startswith("https://"):
            return line
        log.warning("ignoring non-URL line in %s", path)
    return None


# -------------------------------------------------------------------- state


def load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def save_state(state: dict[str, Any], path: Path = STATE_PATH) -> None:
    """Write the mark atomically -- a half-written state file would either
    re-download the album or lose track of it, and both are loud failures."""
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        log.warning("could not write state %s: %s", path, exc)


# ------------------------------------------------------------------ parsing


def _scan_balanced(text: str, start: int) -> str | None:
    """Return the balanced `[...]` beginning at `start`, string-aware.

    `json.JSONDecoder().raw_decode` would do this, except that the surrounding
    object is JavaScript (`{key: 'ds:1', ...}` -- unquoted keys), so the array
    has to be carved out before anything can parse it. Quotes and backslash
    escapes are tracked so a `]` inside a filename cannot end the scan early.
    """
    if start >= len(text) or text[start] != "[":
        return None
    depth = 0
    quote: str | None = None
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if quote is not None:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            continue
        if ch in ('"', "'"):
            quote = ch
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def iter_data_blocks(html: str) -> Iterator[Any]:
    """Every `AF_initDataCallback` payload in the page, parsed.

    A share page carries several (config, strings, the album). Yielding all of
    them and letting the item matcher decide is far more durable than pinning
    on `ds:` numbers, which move between Google deploys.
    """
    for call in _AF_CALL_RE.finditer(html):
        key = _DATA_KEY_RE.search(html, call.end(), call.end() + 4000)
        if not key:
            continue
        bracket = html.find("[", key.end() - 1)
        if bracket < 0:
            continue
        chunk = _scan_balanced(html, bracket)
        if not chunk:
            continue
        try:
            yield json.loads(chunk)
        except ValueError:
            continue


def _as_media(node: list[Any]) -> MediaItem | None:
    """Is this array a media item? `[id, [url, width, height], ts_ms, ...]`.

    Matched structurally rather than positionally-from-the-root, because the
    envelope around the item list changes and the item itself has not. An
    avatar or a UI sprite never appears in this shape.
    """
    if len(node) < 2 or not isinstance(node[0], str) or not node[0]:
        return None
    slot = node[1]
    url: str | None = None
    if isinstance(slot, list) and slot and isinstance(slot[0], str):
        if len(slot) >= 3 and all(isinstance(v, int) for v in slot[1:3]):
            url = slot[0]
    elif isinstance(slot, str):
        url = slot
    if not url or not _MEDIA_HOST_RE.match(url):
        return None
    ts_ms = None
    for value in node[2:5]:
        # A plausible epoch in milliseconds: 2001-09-09 onwards.
        if isinstance(value, int) and value > 1_000_000_000_000:
            ts_ms = value
            break
    return MediaItem(id=node[0], url=url, ts_ms=ts_ms)


def _walk(node: Any, found: dict[str, MediaItem]) -> None:
    if isinstance(node, list):
        item = _as_media(node)
        if item is not None and item.id not in found:
            found[item.id] = item
        for child in node:
            _walk(child, found)
    elif isinstance(node, dict):
        for child in node.values():
            _walk(child, found)


def looks_like_album_page(html: str) -> bool:
    """Did we actually get a Google Photos page, or a login wall / error?

    ★ This distinction is the difference between "the album is empty" and "the
    fetch failed", and they must be handled oppositely: an empty album is a
    perfectly normal state that should still advance the high-water mark, while
    a failed fetch must leave the mark untouched or the next real photo gets
    marked as already-seen and is never delivered.

    A page carrying Google's hydration payload at all is the album page; the
    interstitial and the sign-in wall carry none.
    """
    for _ in iter_data_blocks(html):
        return True
    return False


def extract_media(html: str) -> list[MediaItem]:
    """The album's media items, oldest first.

    Falls back to scraping `/pw/` URLs straight out of the HTML if the
    structured walk finds nothing -- that keeps *some* capability if Google
    reshapes the payload, at the cost of ids that are only the URL itself.
    """
    found: dict[str, MediaItem] = {}
    for block in iter_data_blocks(html):
        _walk(block, found)
    if not found:
        for match in re.finditer(
            r"https://[\w.-]*\.googleusercontent\.com/pw/[A-Za-z0-9_\-]{20,}", html
        ):
            url = match.group(0)
            found.setdefault(url, MediaItem(id=url, url=url))
        if found:
            log.warning("structured parse found nothing; fell back to URL scraping")
    items = list(found.values())
    # Oldest first, so a partial run leaves the newest for next time rather
    # than stranding the oldest forever. Undated items sort last.
    items.sort(key=lambda it: (it.ts_ms is None, it.ts_ms or 0, it.id))
    return items


# ------------------------------------------------------------------ network


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Hand the 30x back to the caller instead of chasing it."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


def resolve_share_url(url: str, timeout: float = PAGE_TIMEOUT_S) -> str:
    """Turn a `photos.app.goo.gl` short link into the real album URL.

    A HEAD with redirects disabled and a non-browser UA -- the only shape that
    yields the `Location` header (see the module docstring). Anything else, or
    any failure, returns the URL unchanged: a link he pasted from the long form
    already is the album, and a shortener hiccup should degrade to "try the URL
    we have" rather than to an exception on a timer job.
    """
    try:
        host = urllib.parse.urlsplit(url).hostname or ""
    except ValueError:
        return url
    if not any(host == h or host.endswith("." + h) for h in SHORTLINK_HOSTS):
        return url
    opener = urllib.request.build_opener(_NoRedirect)
    request = urllib.request.Request(
        url, method="HEAD", headers={"User-Agent": SHORTLINK_UA, "Accept": "*/*"}
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            location = response.headers.get("Location", "")
    except urllib.error.HTTPError as exc:
        # A 302 arrives here once redirect handling is refused.
        location = exc.headers.get("Location", "") if exc.headers else ""
    except (urllib.error.URLError, OSError, ValueError) as exc:
        log.warning("could not resolve short link: %s", exc)
        return url
    location = (location or "").strip()
    if location.startswith("https://") and "photos.google.com" in location:
        log.info("resolved short link to the album page")
        return location
    log.warning("short link did not redirect to an album page; using it as-is")
    return url


def fetch_text(url: str, timeout: float = PAGE_TIMEOUT_S) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    charset = "utf-8"
    try:
        charset = response.headers.get_content_charset() or "utf-8"
    except AttributeError:  # pragma: no cover - non-HTTP responses in tests
        pass
    return raw.decode(charset, errors="replace")


def _safe_name(raw: str, fallback: str) -> str:
    """A filename from an untrusted header. Never a path.

    `Content-Disposition` comes off the network, so `../../.ssh/authorized_keys`
    has to stop being a path here, not later.
    """
    name = _UNSAFE_NAME_RE.sub("_", os.path.basename(raw.strip().strip('"')))
    name = name.lstrip(".")
    return name[:120] if name else fallback


_EXT_BY_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/heic": ".heic",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
}


def _filename_for(item: MediaItem, headers: Any) -> str:
    disposition = ""
    try:
        disposition = headers.get("Content-Disposition", "") or ""
    except AttributeError:  # pragma: no cover
        pass
    match = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", disposition)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    fallback = f"photo-{stamp}-{_safe_name(item.id, 'item')[:16]}"
    if match:
        return _safe_name(match.group(1), fallback)
    ctype = ""
    try:
        ctype = (headers.get("Content-Type", "") or "").split(";")[0].strip().lower()
    except AttributeError:  # pragma: no cover
        pass
    return fallback + _EXT_BY_TYPE.get(ctype, ".jpg")


def _unique(dest_dir: Path, name: str) -> Path:
    target = dest_dir / name
    if not target.exists():
        return target
    stem, dot, ext = name.partition(".")
    for n in range(2, 100):
        candidate = dest_dir / (f"{stem}-{n}{dot}{ext}" if dot else f"{name}-{n}")
        if not candidate.exists():
            return candidate
    return dest_dir / f"{stem}-{int(time.time())}{dot}{ext}"


def download(item: MediaItem, dest_dir: Path, timeout: float = DOWNLOAD_TIMEOUT_S) -> Path | None:
    """Fetch one item at full resolution. Returns the path, or None on failure.

    Downloads to `.part` and renames, so the prompt hook can never pick up a
    half-written image: rename within a directory is atomic, a growing file is
    not.
    """
    request = urllib.request.Request(
        item.download_url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"}
    )
    part: Path | None = None
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            name = _filename_for(item, response.headers)
            target = _unique(dest_dir, name)
            part = target.with_name(target.name + ".part")
            written = 0
            with part.open("wb") as handle:
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > MAX_BYTES:
                        raise ValueError(f"over {MAX_BYTES} bytes")
                    handle.write(chunk)
        if written == 0:
            raise ValueError("empty response")
        part.replace(target)
        log.info("fetched %s (%d bytes) from %s", target, written, item.id)
        return target
    except Exception as exc:  # network, disk, parse -- all the same answer
        log.warning("download failed for %s: %s", item.id, exc)
        if part is not None:
            try:
                part.unlink()
            except OSError:
                pass
        return None


# ---------------------------------------------------------------------- run


def run(
    config_path: Path = CONFIG_PATH,
    state_path: Path = STATE_PATH,
    inbox: Path = INBOX,
    max_items: int = MAX_ITEMS_PER_RUN,
) -> int:
    """One pass. Returns the number of files fetched; never raises."""
    album_url = read_album_url(config_path)
    if not album_url:
        return 0

    try:
        album_url = resolve_share_url(album_url)
        html = fetch_text(album_url)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        log.warning("could not fetch album page: %s", exc)
        return 0
    except Exception as exc:  # pragma: no cover - belt and braces
        log.warning("unexpected error fetching album page: %s", exc)
        return 0

    try:
        items = extract_media(html)
        is_album = looks_like_album_page(html) or bool(items)
    except Exception as exc:
        log.warning("could not parse album page: %s", exc)
        return 0
    if not is_album:
        # A sign-in wall, an error page, or the dynamic-link interstitial. NOT
        # an empty album -- so the mark stays where it is and we try again.
        log.warning("did not get an album page (%d bytes); leaving the mark alone", len(html))
        return 0

    state = load_state(state_path)
    seen: list[str] = [s for s in state.get("seen", []) if isinstance(s, str)]
    seen_set = set(seen)

    if not state.get("primed"):
        # ★ First run marks only. Otherwise turning this on drags his entire
        # album into the inbox, and the one thing worse than missing a photo is
        # 800 of them.
        save_state(
            {
                "primed": True,
                "seen": [it.id for it in items][-SEEN_LIMIT:],
                "last_run": time.time(),
                "version": BRIDGE_VERSION,
            },
            state_path,
        )
        log.info("primed on %d existing item(s); nothing fetched", len(items))
        return 0

    new = [it for it in items if it.id not in seen_set]
    if not new:
        state["last_run"] = time.time()
        save_state(state, state_path)
        return 0
    if len(new) > max_items:
        log.info("%d new item(s); taking %d this run", len(new), max_items)
        new = new[:max_items]

    try:
        inbox.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log.warning("cannot create inbox %s: %s", inbox, exc)
        return 0

    fetched = 0
    for item in new:
        if download(item, inbox) is not None:
            fetched += 1
            seen.append(item.id)
        # A failed item stays unseen, so the next run retries it.
    state["seen"] = seen[-SEEN_LIMIT:]
    state["last_run"] = time.time()
    state["version"] = BRIDGE_VERSION
    save_state(state, state_path)
    if fetched:
        log.info("%d new photo(s) in %s", fetched, inbox)
    return fetched


def _setup_logging(verbose: bool) -> None:
    handlers: list[logging.Handler] = []
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(LOG_PATH, encoding="utf-8"))
    except OSError:
        pass  # a bridge that cannot log still runs
    if verbose or not handlers:
        handlers.append(logging.StreamHandler(sys.stderr))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verbose", action="store_true", help="also log to stderr")
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    try:
        run()
    except Exception as exc:  # launchd must never see this job fail
        log.exception("photo bridge failed: %s", exc)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
