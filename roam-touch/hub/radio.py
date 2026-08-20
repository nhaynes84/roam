"""Internet radio for the wrist: stations from radio-browser.info, cached.

He has no music on the device and no account on it either, so the answer to
"play something" is a **live stream in a plain `<audio>` tag**. This module is
the part that knows *which* streams: it talks to the open
[radio-browser.info](https://www.radio-browser.info/) API -- no key, no
account -- normalises what comes back, and caches it to disk.

★ **The browser never calls that API.** Three reasons, in order of how much
they hurt: the client is Chrome 74 and every third-party endpoint is one CORS
header away from being a blank list it cannot explain; the API's mirrors come
and go, and a fallback loop is server work; and a cache on talos means the
station list opens instantly on the wrist and still opens when the API is down
or the phone is on a bad link. The page only ever talks to the hub.

★ **A station is only offered if this engine can actually play it.** That is a
narrow filter and it is deliberate -- see `playable`. HLS (`.m3u8`) needs MSE
plumbing and a library; a `.pls`/`.m3u` is a playlist file, and `<audio>` hands
it straight to the decoder and fails; anything but MP3/AAC is a coin toss on a
2019 Android engine. A station that appears in the list and then produces
silence is worse than one that was never offered, because from his arm the two
look identical.

**Favourites are baked in, and then refreshed.** `FAVOURITES` holds the
station uuid *and* a known-good stream URL for each: a fresh install with no
network still shows a full list that plays. A successful refresh replaces the
name/url/bitrate from the API (URLs do rot -- that is why the API exists) and
keeps the curated order. A failed one is not an error, just yesterday's list.

Kept out of `hub.py` for the same reason `files.py` is: it is the part with a
network dependency and a parser, and a plain function taking a string is far
easier to point a hundred nasty inputs at than a route is.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable

log = logging.getLogger("roam.hub.radio")

#: API mirrors, tried in order. `all.` is the round-robin the project
#: advertises; the named ones are the fallback for when its DNS is unhappy.
#: ⚠️ Several mirrors listed in old docs (at1, nl1, fi1) no longer resolve at
#: all -- verified 2026-08-14. Do not "restore" them; they cost a DNS timeout
#: each on the way to the one that works.
MIRRORS: tuple[str, ...] = (
    "https://all.api.radio-browser.info",
    "https://de1.api.radio-browser.info",
    "https://de2.api.radio-browser.info",
)

#: radio-browser asks every client to identify itself. Being anonymous here
#: gets you rate-limited, and rightly so.
USER_AGENT = "roam-touch-hub/1.0 (+https://github.com/ - one wearer, one wrist)"

HTTP_TIMEOUT_S = 12.0
#: A station list is not news. An hour is plenty fresh for search, and the
#: curated list only changes when a station moves its stream.
SEARCH_TTL_S = 3600.0
FAVOURITES_TTL_S = 24 * 3600.0

DEFAULT_CACHE_DIR = Path.home() / "Library" / "Caches" / "roam-hub" / "radio"

#: What a search may return, after filtering. A wrist-sized list: he is going
#: to scroll it with one thumb at arm's length, not browse a directory.
SEARCH_LIMIT = 30
#: ...and how many to ask for, because most of what comes back is filtered out.
FETCH_MULTIPLIER = 6
MAX_FETCH = 300
MAX_QUERY_CHARS = 64

#: ★ Codecs Chrome 74 on Android will actually decode from a bare `<audio>`.
#: MP3 and ADTS AAC (including HE-AAC, which radio-browser spells `AAC+`) are
#: safe. OGG/Vorbis is *usually* fine and FLAC-over-HTTP usually is not, but
#: "usually" on the only device he owns is not a good enough reason to put a
#: station in front of him.
PLAYABLE_CODECS = frozenset({"MP3", "AAC", "AAC+", "AACP"})

#: A URL that is a *playlist*, not a stream. `<audio src=".../foo.pls">` does
#: not follow it -- it feeds the text to the decoder, which fails silently.
PLAYLIST_SUFFIXES = (".pls", ".m3u", ".m3u8", ".asx", ".ram", ".xspf")


class RadioError(RuntimeError):
    """Something the client is allowed to be told. Never a filesystem path."""


class RadioUnavailable(RadioError):
    """Every mirror refused, and there was nothing cached to fall back to."""


#: The curated set. Order is the order they appear on his wrist, so the two
#: he actually reaches for are first. Every `url` here was fetched and checked
#: to answer `audio/mpeg` or `audio/aac` on 2026-08-14; they are the fallback
#: when the API cannot be reached, not decoration.
FAVOURITES: tuple[dict[str, Any], ...] = (
    {
        "uuid": "960cf833-0601-11e8-ae97-52543be04c81",
        "name": "SomaFM Groove Salad",
        "url": "https://ice5.somafm.com/groovesalad-128-mp3",
        "codec": "MP3", "bitrate": 128, "tags": "ambient, downtempo",
    },
    {
        "uuid": "d61e880e-e8f0-11e9-a96c-52543be04c81",
        "name": "Radio Paradise Main Mix",
        "url": "http://stream.radioparadise.com/aac-128",
        "codec": "AAC", "bitrate": 128, "tags": "eclectic, rock",
    },
    {
        "uuid": "e9fddd49-3ee2-4597-8574-1b7dbd00aac0",
        "name": "KEXP 90.3 Seattle",
        "url": "https://kexp-mp3-128.streamguys1.com/kexp128.mp3",
        "codec": "MP3", "bitrate": 128, "tags": "indie, live dj",
    },
    {
        "uuid": "960eb2e9-0601-11e8-ae97-52543be04c81",
        "name": "SomaFM Drone Zone",
        "url": "https://ice4.somafm.com/dronezone-128-mp3",
        "codec": "MP3", "bitrate": 128, "tags": "ambient, focus",
    },
    {
        "uuid": "960c7c81-0601-11e8-ae97-52543be04c81",
        "name": "SomaFM Secret Agent",
        "url": "https://ice6.somafm.com/secretagent-128-mp3",
        "codec": "MP3", "bitrate": 128, "tags": "spy jazz, lounge",
    },
    {
        "uuid": "9a5811ad-f4b5-11e8-a471-52543be04c81",
        "name": "SomaFM Metal Detector",
        "url": "https://ice5.somafm.com/metal-128-mp3",
        "codec": "MP3", "bitrate": 128, "tags": "metal, doom",
    },
    {
        "uuid": "932eb148-e6f6-11e9-a96c-52543be04c81",
        "name": "FIP",
        "url": "http://icecast.radiofrance.fr/fip-hifi.aac",
        "codec": "AAC", "bitrate": 192, "tags": "eclectic, france",
    },
    {
        "uuid": "961ac56b-0601-11e8-ae97-52543be04c81",
        "name": "Radio Swiss Jazz",
        "url": "http://stream.srg-ssr.ch/m/rsj/mp3_128",
        "codec": "MP3", "bitrate": 128, "tags": "jazz",
    },
    {
        "uuid": "c60cb1ef-b88f-4bbc-a24b-e911a534259f",
        "name": "Jazz24",
        "url": "https://knkx-live-a.edge.audiocdn.com/6285_128k",
        "codec": "MP3", "bitrate": 128, "tags": "jazz",
    },
    {
        "uuid": "960a4ad1-0601-11e8-ae97-52543be04c81",
        "name": "WWOZ New Orleans",
        "url": "http://wwoz-sc.streamguys.com/wwoz-hi.mp3",
        "codec": "MP3", "bitrate": 128, "tags": "blues, new orleans",
    },
    {
        "uuid": "6b4d2d9d-1435-44aa-b5ee-1db50f833ddc",
        "name": "Venice Classic Radio",
        "url": "https://uk2.streamingpulse.com/ssl/vcr1",
        "codec": "MP3", "bitrate": 128, "tags": "classical",
    },
    {
        "uuid": "598c4d0e-6b06-43fb-bff4-717c591213a9",
        "name": "BBC World Service",
        "url": "https://stream.live.vc.bbcmedia.co.uk/bbc_world_service",
        "codec": "MP3", "bitrate": 56, "tags": "news, talk",
    },
)


# ------------------------------------------------------------------ shaping


def _text(value: Any, limit: int) -> str:
    """A field off the network, made safe to put in a JSON body and a page.

    Control characters are stripped rather than escaped: a station name is a
    label on a button, and nothing about it needs a newline. The length cap is
    what stops one absurd entry from making the list unreadable.
    """
    if not isinstance(value, str):
        return ""
    cleaned = "".join(c for c in value if c == " " or c.isprintable())
    return cleaned.strip()[:limit]


def playable(raw: dict[str, Any]) -> bool:
    """Can Chrome 74 on a Pixel 1 play this from a bare `<audio>` tag?

    ★ Four ways a station gets dropped, all of them things that would look
    like "the radio is broken" from his arm:

    * `hls: 1` -- a manifest, not a stream. Needs MSE and a library.
    * a playlist URL -- `<audio>` feeds the `.pls` text to the decoder.
    * a codec outside `PLAYABLE_CODECS`, including the very common `UNKNOWN`,
      which is radio-browser saying it could not tell either.
    * `lastcheckok: 0` -- their own checker could not reach it.
    """
    if raw.get("hls"):
        return False
    if raw.get("lastcheckok") not in (1, "1", None):
        return False
    codec = _text(raw.get("codec"), 16).upper()
    if codec not in PLAYABLE_CODECS:
        return False
    url = _text(raw.get("url_resolved") or raw.get("url"), 2048)
    if not url.lower().startswith(("http://", "https://")):
        return False
    path = urllib.parse.urlsplit(url).path.lower()
    return not path.endswith(PLAYLIST_SUFFIXES)


def normalise(raw: dict[str, Any]) -> dict[str, Any]:
    """One API station -> the six fields the page uses, and nothing else.

    Dropping the other thirty is not tidiness: every field kept is a field
    that has to be escaped somewhere, and `geo_distance` is never going to be
    read at arm's length.
    """
    return {
        "uuid": _text(raw.get("stationuuid"), 64),
        "name": _text(raw.get("name"), 80) or "unnamed station",
        "url": _text(raw.get("url_resolved") or raw.get("url"), 2048),
        "codec": _text(raw.get("codec"), 16).upper(),
        "bitrate": int(raw.get("bitrate") or 0),
        "tags": ", ".join(
            t for t in _text(raw.get("tags"), 120).split(",") if t
        )[:60],
    }


# ----------------------------------------------------------------- fetching


def _fetch(path: str, params: dict[str, str], timeout: float) -> list[dict[str, Any]]:
    """One API call, against the first mirror that answers.

    Mirrors go away -- three of the five in the project's own documentation no
    longer resolve. Trying the next one is the difference between "no radio
    today" and a half-second delay nobody notices.
    """
    query = urllib.parse.urlencode(params)
    last: Exception | None = None
    for base in MIRRORS:
        url = base + path + ("?" + query if query else "")
        request = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8", "replace"))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            log.warning("radio-browser mirror %s failed: %s", base, exc)
            last = exc
            continue
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        last = ValueError("unexpected payload shape")
    raise RadioUnavailable(f"radio-browser is unreachable ({last})")


# -------------------------------------------------------------------- cache


def _cache_path(cache_dir: Path, key: str) -> Path:
    return cache_dir / (hashlib.sha1(key.encode("utf-8")).hexdigest() + ".json")


def cache_read(cache_dir: Path, key: str) -> dict[str, Any] | None:
    """Whatever is on disk for this key, however old. `None` if unreadable.

    Age is the caller's business: a stale list is the right answer when the
    network is down and the wrong one when it is not.
    """
    try:
        payload = json.loads(_cache_path(cache_dir, key).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("stations"), list):
        return None
    return payload


def cache_write(cache_dir: Path, key: str, stations: list[dict[str, Any]]) -> None:
    """Atomically, via `.part` -- a half-written cache file reads as garbage
    and would poison every later request until someone deleted it by hand."""
    target = _cache_path(cache_dir, key)
    part = target.with_name(target.name + ".part")
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        part.write_text(
            json.dumps({"fetched_at": time.time(), "stations": stations}),
            encoding="utf-8",
        )
        part.replace(target)
    except OSError as exc:  # a full disk must not take the radio down
        log.warning("could not cache %r: %s", key, exc)
        try:
            part.unlink()
        except OSError:
            pass


# ------------------------------------------------------------------ queries


def _dedupe(stations: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """One entry per stream URL. The database is full of the same station
    entered five times, and five identical buttons is a broken-looking page."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for station in stations:
        if not station.get("url") or station["url"] in seen:
            continue
        seen.add(station["url"])
        out.append(station)
    return out


def clean_query(raw: str) -> str:
    """What the user typed, made into something worth sending upstream."""
    return _text(raw, MAX_QUERY_CHARS).strip()


def favourites(
    cache_dir: Path = DEFAULT_CACHE_DIR,
    ttl: float = FAVOURITES_TTL_S,
    now: float | None = None,
) -> dict[str, Any]:
    """The curated list, refreshed from the API at most once a day.

    ★ **Never fails.** The baked-in URL is used for any station the API did not
    return, could not be trusted to be playable, or was not asked about because
    the network was down. The list he sees is always the full list, in the same
    order, whatever the internet is doing -- the worst case is one dead station
    rather than an empty page.
    """
    now = time.time() if now is None else now
    key = "favourites/v1"
    cached = cache_read(cache_dir, key)
    if cached is not None and now - float(cached.get("fetched_at") or 0) < ttl:
        return {
            "kind": "favourites",
            "query": "",
            "source": "cache",
            "fetched_at": cached.get("fetched_at"),
            "stations": _merge_favourites(cached["stations"]),
        }
    try:
        raw = _fetch(
            "/json/stations/byuuid",
            {"uuids": ",".join(f["uuid"] for f in FAVOURITES)},
            HTTP_TIMEOUT_S,
        )
    except RadioError:
        if cached is not None:
            return {
                "kind": "favourites",
                "query": "",
                "source": "stale",
                "fetched_at": cached.get("fetched_at"),
                "stations": _merge_favourites(cached["stations"]),
            }
        return {
            "kind": "favourites",
            "query": "",
            "source": "builtin",
            "fetched_at": None,
            "stations": _merge_favourites([]),
        }
    fresh = [normalise(item) for item in raw if playable(item)]
    cache_write(cache_dir, key, fresh)
    return {
        "kind": "favourites",
        "query": "",
        "source": "live",
        "fetched_at": now,
        "stations": _merge_favourites(fresh),
    }


def _merge_favourites(fresh: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Curated order and curated *names*, live stream URLs.

    The API is the authority on a station's **stream URL** -- they rot, and
    that is the whole reason for talking to it -- and the baked-in entry is the
    authority on everything he reads. The directory calls one of these
    "SomaFM Groove Salad (128k MP3)", which is four words of noise on a strip
    of screen the width of a wrist. So the loop is over `FAVOURITES`, not over
    the response, and only `url`/`codec`/`bitrate` cross over.
    """
    by_uuid = {s.get("uuid"): s for s in fresh if s.get("uuid")}
    merged: list[dict[str, Any]] = []
    for entry in FAVOURITES:
        live = by_uuid.get(entry["uuid"])
        usable = bool(live and live.get("url"))
        merged.append(
            {
                "uuid": entry["uuid"],
                "name": entry["name"],
                "url": live["url"] if usable else entry["url"],
                "codec": (live["codec"] if usable else "") or entry["codec"],
                "bitrate": (live["bitrate"] if usable else 0) or entry["bitrate"],
                "tags": entry["tags"],
            }
        )
    return merged


def search(
    query: str,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    ttl: float = SEARCH_TTL_S,
    limit: int = SEARCH_LIMIT,
    now: float | None = None,
) -> dict[str, Any]:
    """Stations whose name matches, most-played first.

    Asks for far more than it returns, because `playable` throws most of it
    away: a name search for "jazz" comes back thick with HLS manifests and
    `UNKNOWN` codecs, and a page that says "no results" when there were
    forty is not the truth either.
    """
    now = time.time() if now is None else now
    cleaned = clean_query(query)
    if not cleaned:
        raise RadioError("empty search")
    key = "search/v1/" + cleaned.lower()
    cached = cache_read(cache_dir, key)
    if cached is not None and now - float(cached.get("fetched_at") or 0) < ttl:
        return {
            "kind": "search",
            "query": cleaned,
            "source": "cache",
            "fetched_at": cached.get("fetched_at"),
            "stations": cached["stations"][:limit],
        }
    try:
        raw = _fetch(
            "/json/stations/search",
            {
                "name": cleaned,
                "limit": str(min(limit * FETCH_MULTIPLIER, MAX_FETCH)),
                "hidebroken": "true",
                "order": "clickcount",
                "reverse": "true",
            },
            HTTP_TIMEOUT_S,
        )
    except RadioError:
        if cached is not None:
            return {
                "kind": "search",
                "query": cleaned,
                "source": "stale",
                "fetched_at": cached.get("fetched_at"),
                "stations": cached["stations"][:limit],
            }
        raise
    stations = _dedupe(normalise(item) for item in raw if playable(item))
    cache_write(cache_dir, key, stations)
    return {
        "kind": "search",
        "query": cleaned,
        "source": "live",
        "fetched_at": now,
        "stations": stations[:limit],
    }


def stations(
    query: str = "",
    cache_dir: Path = DEFAULT_CACHE_DIR,
    now: float | None = None,
) -> dict[str, Any]:
    """One entry point for the page: no query means the curated list."""
    if clean_query(query):
        return search(query, cache_dir=cache_dir, now=now)
    return favourites(cache_dir=cache_dir, now=now)
