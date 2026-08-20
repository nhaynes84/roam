"""The radio: which streams are offered, what happens when the API is down.

Two questions run through this file. The first is **"can he actually hear
it?"** -- a station that appears on his wrist and then produces silence is
worse than one that was never listed, so `playable` is pushed at HLS
manifests, playlist URLs, exotic codecs and dead entries. The second is
**"what happens when radio-browser.info is not there?"**, which on a wrist is
not a hypothetical: the answer has to be a list that still plays, not a
spinner.

The network is mocked at exactly one boundary -- `urllib.request.urlopen`
inside `radio.py` -- so mirror failover, JSON decoding and the cache all run
for real. ★ Nothing in this file may touch the internet or the real cache
directory; `no_network` fails loudly if a test forgets.

The page's own 2019-browser contract (acorn at ecmaVersion 2019, the CSS
blacklist) is parametrized over `radio.html` in `test_files_api.py`, where
browse.html and stl.html already are -- one list, one place to add a page.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
import urllib.error
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import hub as hub_mod
import radio as radio_mod
from conftest import TOKEN

HUB_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = HUB_DIR / "web"


# ------------------------------------------------------------- the fake API


def station(**overrides):
    """A radio-browser station, playable unless a test says otherwise."""
    base = {
        "stationuuid": "uuid-1",
        "name": "Test FM",
        "url": "http://example.test/one.mp3",
        "url_resolved": "http://example.test/one.mp3",
        "codec": "MP3",
        "bitrate": 128,
        "hls": 0,
        "lastcheckok": 1,
        "tags": "jazz,test",
        "country": "Nowhere",
    }
    base.update(overrides)
    return base


class FakeHTTP:
    """Records every URL asked for and answers from a script.

    `answers` is consumed one call at a time; an entry that is an exception is
    raised instead of returned, which is how mirror failover is tested.
    """

    def __init__(self, answers):
        self.answers = list(answers)
        self.urls: list[str] = []
        self.headers: list[dict] = []

    def __call__(self, request, timeout=None):
        self.urls.append(request.full_url)
        self.headers.append(dict(request.headers))
        answer = self.answers.pop(0) if self.answers else []
        if isinstance(answer, Exception):
            raise answer
        return _Body(json.dumps(answer).encode("utf-8"))


class _Body:
    def __init__(self, raw: bytes):
        self.raw = raw

    def read(self):
        return self.raw

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any test that does not install its own fake gets a loud failure."""
    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to reach the real internet")

    monkeypatch.setattr(radio_mod.urllib.request, "urlopen", refuse)


@pytest.fixture
def http(monkeypatch):
    def install(*answers):
        fake = FakeHTTP(answers)
        monkeypatch.setattr(radio_mod.urllib.request, "urlopen", fake)
        return fake

    return install


@pytest.fixture
def cache(tmp_path) -> Path:
    return tmp_path / "radio-cache"


@pytest.fixture
def radio_client(tmp_path, store, fake_tmux):
    settings = hub_mod.Settings(
        token=TOKEN,
        db_path=tmp_path / "hub.sqlite",
        token_file=tmp_path / "token.txt",
        poll_interval=0.05,
        radio_cache=tmp_path / "radio-cache",
    )
    app = hub_mod.create_app(settings=settings, store=store)
    with TestClient(app) as c:
        yield c


# ------------------------------------------------------- what he can hear


UNPLAYABLE = [
    ("an HLS manifest", station(hls=1, url_resolved="http://x.test/a.m3u8")),
    ("an .m3u8 without the flag", station(url_resolved="http://x.test/a.m3u8")),
    ("a .pls playlist", station(url_resolved="http://x.test/a.pls")),
    ("an .m3u playlist", station(url_resolved="http://x.test/a.m3u")),
    ("an .asx playlist", station(url_resolved="http://x.test/a.asx")),
    ("an unknown codec", station(codec="UNKNOWN")),
    ("FLAC", station(codec="FLAC")),
    ("OGG", station(codec="OGG")),
    ("a station their checker cannot reach", station(lastcheckok=0)),
    ("a non-http scheme", station(url_resolved="rtsp://x.test/a")),
    ("no url at all", station(url="", url_resolved="")),
]


@pytest.mark.parametrize("why, raw", UNPLAYABLE, ids=[c[0] for c in UNPLAYABLE])
def test_a_station_this_engine_cannot_play_is_never_offered(why, raw):
    assert not radio_mod.playable(raw), why


@pytest.mark.parametrize("codec", ["MP3", "AAC", "AAC+", "aac"])
def test_mp3_and_aac_are_offered(codec):
    assert radio_mod.playable(station(codec=codec))


def test_a_query_string_does_not_make_a_url_look_like_a_playlist():
    """`.../6285_128k?playerid=...` is a real stream. Suffix matching on the
    *path*, not on the whole URL, is what keeps it in the list."""
    assert radio_mod.playable(
        station(url_resolved="https://cdn.test/6285_128k?x=a.m3u&uuid=1")
    )


def test_normalise_keeps_six_fields_and_drops_the_other_thirty():
    out = radio_mod.normalise(station(geo_lat=1.5, votes=99))
    assert set(out) == {"uuid", "name", "url", "codec", "bitrate", "tags"}
    assert out["bitrate"] == 128 and out["codec"] == "MP3"


def test_normalise_strips_control_characters_and_caps_length():
    out = radio_mod.normalise(
        station(name="Bad\x07Name\n" + "x" * 200, tags="a,,b", bitrate=None)
    )
    assert out["name"].startswith("BadName")
    assert "\x07" not in out["name"] and "\n" not in out["name"]
    assert len(out["name"]) <= 80
    assert out["tags"] == "a, b"
    assert out["bitrate"] == 0


def test_an_unnamed_station_still_gets_a_label():
    assert radio_mod.normalise(station(name=""))["name"] == "unnamed station"


# ------------------------------------------------------------- favourites


def test_favourites_are_the_curated_list_in_the_curated_order(http, cache):
    http([station(stationuuid=f["uuid"], name="live " + f["name"]) for f in radio_mod.FAVOURITES])
    body = radio_mod.favourites(cache)
    assert body["source"] == "live"
    assert [s["uuid"] for s in body["stations"]] == [
        f["uuid"] for f in radio_mod.FAVOURITES
    ]


def test_the_curated_name_wins_over_the_directorys(http, cache):
    """The directory calls one of these "SomaFM Groove Salad (128k MP3)".
    Four words of noise on a strip of screen the width of a wrist."""
    first = radio_mod.FAVOURITES[0]
    http([station(stationuuid=first["uuid"], name=first["name"] + " (128k MP3)",
                  url_resolved="http://new.test/a.mp3")])
    top = radio_mod.favourites(cache)["stations"][0]
    assert top["name"] == first["name"]
    assert top["url"] == "http://new.test/a.mp3"


def test_a_favourite_the_api_forgot_falls_back_to_the_baked_in_url(http, cache):
    """★ The list is always the whole list. One dead station beats an empty
    page on a device with no other way to play music."""
    first = radio_mod.FAVOURITES[0]
    http([station(stationuuid=first["uuid"], url_resolved="http://new.test/a.mp3")])
    body = radio_mod.favourites(cache)
    assert len(body["stations"]) == len(radio_mod.FAVOURITES)
    assert body["stations"][0]["url"] == "http://new.test/a.mp3"
    assert body["stations"][1]["url"] == radio_mod.FAVOURITES[1]["url"]


def test_an_unplayable_favourite_from_the_api_is_ignored_not_shown(http, cache):
    """If the directory now says a favourite is HLS, the known-good URL wins
    over a stream that would fail on his wrist."""
    first = radio_mod.FAVOURITES[0]
    http([station(stationuuid=first["uuid"], hls=1,
                  url_resolved="http://new.test/a.m3u8")])
    body = radio_mod.favourites(cache)
    assert body["stations"][0]["url"] == first["url"]


def test_favourites_survive_the_directory_being_down(http, cache):
    http(*[urllib.error.URLError("no route")] * len(radio_mod.MIRRORS))
    body = radio_mod.favourites(cache)
    assert body["source"] == "builtin"
    assert [s["url"] for s in body["stations"]] == [
        f["url"] for f in radio_mod.FAVOURITES
    ]


def test_favourites_come_from_the_cache_second_time(http, cache):
    fake = http([station(stationuuid=radio_mod.FAVOURITES[0]["uuid"])])
    radio_mod.favourites(cache)
    body = radio_mod.favourites(cache)
    assert body["source"] == "cache"
    assert len(fake.urls) == 1, "the cache did not stop a second fetch"


def test_a_stale_cache_beats_no_list_at_all(http, cache):
    fake = http(
        [station(stationuuid=radio_mod.FAVOURITES[0]["uuid"],
                 url_resolved="http://cached.test/a.mp3")],
        *[urllib.error.URLError("down")] * len(radio_mod.MIRRORS),
    )
    radio_mod.favourites(cache)
    later = time.time() + radio_mod.FAVOURITES_TTL_S + 60
    body = radio_mod.favourites(cache, now=later)
    assert body["source"] == "stale"
    assert body["stations"][0]["url"] == "http://cached.test/a.mp3"
    assert len(fake.urls) == 1 + len(radio_mod.MIRRORS)


# ----------------------------------------------------------------- search


def test_search_filters_and_dedupes(http, cache):
    http([
        station(stationuuid="a", url_resolved="http://x.test/1.mp3"),
        station(stationuuid="b", url_resolved="http://x.test/1.mp3"),  # same stream
        station(stationuuid="c", url_resolved="http://x.test/2.m3u8", hls=1),
        station(stationuuid="d", url_resolved="http://x.test/3.mp3", codec="UNKNOWN"),
        station(stationuuid="e", url_resolved="http://x.test/4.aac", codec="AAC"),
    ])
    body = radio_mod.search("jazz", cache)
    assert [s["uuid"] for s in body["stations"]] == ["a", "e"]
    assert body["query"] == "jazz" and body["source"] == "live"


def test_search_asks_for_more_than_it_returns(http, cache):
    """Most of a name search is filtered out; asking for exactly 30 would
    routinely answer with four."""
    fake = http([])
    radio_mod.search("jazz", cache)
    assert "hidebroken=true" in fake.urls[0]
    assert "limit=%d" % (radio_mod.SEARCH_LIMIT * radio_mod.FETCH_MULTIPLIER) in fake.urls[0]
    assert "name=jazz" in fake.urls[0]


def test_search_caps_what_it_returns(http, cache):
    http([station(stationuuid=str(i), url_resolved="http://x.test/%d.mp3" % i)
          for i in range(80)])
    body = radio_mod.search("many", cache)
    assert len(body["stations"]) == radio_mod.SEARCH_LIMIT


def test_an_empty_search_is_refused_not_sent_upstream(cache):
    for blank in ("", "   ", "\x00\x07"):
        with pytest.raises(radio_mod.RadioError):
            radio_mod.search(blank, cache)


def test_a_long_query_is_truncated_rather_than_sent_whole(http, cache):
    fake = http([])
    body = radio_mod.search("x" * 400, cache)
    assert len(body["query"]) == radio_mod.MAX_QUERY_CHARS
    assert "x" * (radio_mod.MAX_QUERY_CHARS + 1) not in fake.urls[0]


def test_search_with_nothing_cached_and_no_network_is_an_error(http, cache):
    http(*[urllib.error.URLError("down")] * len(radio_mod.MIRRORS))
    with pytest.raises(radio_mod.RadioUnavailable):
        radio_mod.search("jazz", cache)


def test_search_falls_back_to_its_own_stale_cache(http, cache):
    http([station(stationuuid="a", url_resolved="http://x.test/1.mp3")],
         *[urllib.error.URLError("down")] * len(radio_mod.MIRRORS))
    radio_mod.search("jazz", cache)
    body = radio_mod.search("jazz", cache, now=time.time() + radio_mod.SEARCH_TTL_S + 1)
    assert body["source"] == "stale" and body["stations"][0]["uuid"] == "a"


def test_the_cache_key_is_case_insensitive(http, cache):
    fake = http([station()])
    radio_mod.search("Jazz", cache)
    radio_mod.search("jAZZ", cache)
    assert len(fake.urls) == 1


# ------------------------------------------------------------ the plumbing


def test_the_next_mirror_is_tried_when_one_is_down(http, cache):
    fake = http(urllib.error.URLError("dns"), [station()])
    radio_mod.search("jazz", cache)
    assert len(fake.urls) == 2
    assert fake.urls[0].startswith(radio_mod.MIRRORS[0])
    assert fake.urls[1].startswith(radio_mod.MIRRORS[1])


def test_every_request_identifies_itself(http, cache):
    """radio-browser asks clients to send a User-Agent, and rate-limits the
    ones that do not."""
    fake = http([station()])
    radio_mod.search("jazz", cache)
    agent = [v for k, v in fake.headers[0].items() if k.lower() == "user-agent"]
    assert agent and "roam-touch-hub" in agent[0]


def test_junk_from_the_api_does_not_become_a_station(http, cache):
    http(["a string", 42, None, station(stationuuid="ok")])
    body = radio_mod.search("jazz", cache)
    assert [s["uuid"] for s in body["stations"]] == ["ok"]


def test_a_non_list_payload_is_treated_as_a_dead_mirror(http, cache):
    http(*[{"error": "nope"}] * len(radio_mod.MIRRORS))
    with pytest.raises(radio_mod.RadioUnavailable):
        radio_mod.search("jazz", cache)


def test_the_cache_is_written_atomically(http, cache):
    http([station()])
    radio_mod.search("jazz", cache)
    assert not [p for p in cache.iterdir() if p.name.endswith(".part")]


def test_a_corrupt_cache_file_is_ignored_not_fatal(http, cache):
    http([station()])
    radio_mod.search("jazz", cache)
    for path in cache.iterdir():
        path.write_text("{ this is not json", encoding="utf-8")
    http([station(stationuuid="fresh")])
    assert radio_mod.search("jazz", cache)["stations"][0]["uuid"] == "fresh"


def test_an_unwritable_cache_does_not_take_the_radio_down(http, cache, monkeypatch):
    http([station()])
    monkeypatch.setattr(
        radio_mod.Path, "write_text",
        lambda *a, **kw: (_ for _ in ()).throw(OSError("read-only")),
    )
    assert radio_mod.search("jazz", cache)["stations"]


def test_stations_dispatches_on_whether_there_is_a_query(http, cache):
    http([station(stationuuid="s")])
    assert radio_mod.stations("", cache)["kind"] == "favourites"
    assert radio_mod.stations("  ", cache)["kind"] == "favourites"
    http([station(stationuuid="s")])
    assert radio_mod.stations("jazz", cache)["kind"] == "search"


# ------------------------------------------------------------- the routes


@pytest.mark.parametrize("path", ["/radio", "/radio/stations"])
def test_every_radio_endpoint_needs_the_token(radio_client, path):
    assert radio_client.get(path).status_code == 401


def test_a_query_token_works_because_a_navigation_cannot_send_a_header(radio_client):
    assert radio_client.get("/radio", params={"token": TOKEN}).status_code == 200


def test_stations_answers_the_favourites_by_default(radio_client, auth, http):
    http(*[urllib.error.URLError("offline")] * len(radio_mod.MIRRORS))
    body = radio_client.get("/radio/stations", headers=auth).json()
    assert body["kind"] == "favourites"
    assert len(body["stations"]) == len(radio_mod.FAVOURITES)
    assert body["source"] == "builtin"


def test_stations_passes_a_search_through(radio_client, auth, http):
    fake = http([station(stationuuid="a", name="Jazz FM")])
    body = radio_client.get("/radio/stations", params={"q": "jazz"}, headers=auth).json()
    assert body["kind"] == "search" and body["stations"][0]["name"] == "Jazz FM"
    assert "name=jazz" in fake.urls[0]


def test_a_search_with_nothing_behind_it_is_a_502_not_a_500(radio_client, auth, http):
    """The hub is fine; the directory is not. A 500 would send the client
    looking for a bug on this side."""
    http(*[urllib.error.URLError("down")] * len(radio_mod.MIRRORS))
    response = radio_client.get(
        "/radio/stations", params={"q": "jazz"}, headers=auth
    )
    assert response.status_code == 502


def test_an_over_long_query_is_rejected_by_the_route(radio_client, auth):
    response = radio_client.get(
        "/radio/stations", params={"q": "x" * 500}, headers=auth
    )
    assert response.status_code == 422


def test_the_radio_page_carries_the_token_and_no_referrer(radio_client, auth):
    response = radio_client.get("/radio", headers=auth)
    assert response.status_code == 200
    assert TOKEN in response.text
    assert "__ROAM_TOKEN__" not in response.text
    assert response.headers["referrer-policy"] == "no-referrer"


# --------------------------------------------------------------- the page


PAGE = (WEB_DIR / "radio.html").read_text(encoding="utf-8")


def test_the_page_plays_with_a_plain_audio_element():
    assert re.search(r"<audio[^>]*id=\"audio\"", PAGE)
    assert "preload=\"none\"" in PAGE


def test_the_page_pulls_in_nothing_from_the_internet():
    """★ No CDN, no station favicon, no analytics. Everything it needs comes
    from the hub, which is the only host it can be sure of reaching -- and the
    only one that should ever see the token."""
    for src in re.findall(r"(?:src|href)=\"([^\"]+)\"", PAGE):
        assert not src.startswith("http"), src


def test_the_page_hangs_up_rather_than_only_pausing():
    """⚠️ `audio.pause()` alone leaves the connection open and the buffer
    filling -- a radio he cannot hear, still using the battery."""
    assert "removeAttribute(\"src\")" in PAGE


def test_the_page_never_reaches_for_hls():
    lowered = PAGE.lower()
    for banned in ("hls.js", ".m3u8", "mediasource", "sourcebuffer"):
        assert banned not in lowered, banned


def test_the_page_keeps_both_halves_of_the_nexus_audio_contract():
    """★★ The app was written before this page existed and already expects it:
    `window.RoamRadio` is the hook it prefers over poking `<audio>` elements
    (nexus/.../audio/WebViewPlayback.kt: `RadioJs.HOOK`), and `RoamAudio` is how
    it learns music is wanted so it holds media focus only while it is. Without
    the first, a PTT resume tries to restart an element whose src this page
    dropped on purpose; without the second, an incoming call plays over it."""
    assert "window.RoamRadio" in PAGE
    for method in ("play:", "pause:", "setVolume:"):
        assert method in PAGE, method
    assert "window.RoamAudio" in PAGE
    for hook in ("onPlay", "onPause"):
        assert hook in PAGE, hook


# ------------------------------------------------- the player, actually run

#: A browser-shaped sandbox, small enough to read. Everything the page's script
#: touches and nothing else: the DOM calls it makes, `fetch`, the timers and the
#: two objects the Nexus app injects. ★ The point is the *state machine* -- who
#: may start the stream, who may stop it, and what a dropped connection means --
#: which is the part that cannot be checked from Python and would otherwise only
#: be found out on his arm.
DRIVER = r"""
const fs = require("fs"), vm = require("vm");
const html = fs.readFileSync(process.argv[2], "utf8");
const source = (html.match(/<script>([\s\S]*?)<\/script>/) || [])[1];
if (!source) { throw new Error("no inline script in the page"); }

function fail(message) { console.error("FAIL: " + message); process.exit(1); }
function assert(ok, message) { if (!ok) { fail(message); } }

function El(tag) {
  this.tag = tag; this.children = []; this.attrs = {}; this.listeners = {};
  this.className = ""; this.textContent = ""; this.value = ""; this.src = "";
  this.disabled = false; this.paused = true; this.volume = 1;
}
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.setAttribute = function (k, v) {
  this.attrs[k] = String(v); if (k === "src") { this.src = String(v); }
};
El.prototype.getAttribute = function (k) {
  return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null;
};
El.prototype.removeAttribute = function (k) {
  delete this.attrs[k]; if (k === "src") { this.src = ""; }
};
El.prototype.addEventListener = function (t, f) {
  (this.listeners[t] = this.listeners[t] || []).push(f);
};
El.prototype.fire = function (t) {
  (this.listeners[t] || []).forEach(function (f) { f({ preventDefault: function () {} }); });
};
El.prototype.click = function () { this.fire("click"); };
El.prototype.getElementsByClassName = function (cls) {
  const out = [];
  (function walk(node) {
    node.children.forEach(function (c) {
      if ((" " + c.className + " ").indexOf(" " + cls + " ") >= 0) { out.push(c); }
      walk(c);
    });
  })(this);
  return out;
};
Object.defineProperty(El.prototype, "innerHTML",
  { get: function () { return ""; }, set: function () { this.children = []; } });

const audio = new El("audio");
audio.plays = 0;
audio.play = function () { audio.plays++; audio.paused = false; return Promise.resolve(); };
audio.load = function () {};
audio.pause = function () { audio.paused = true; };

const ids = {
  audio: audio, list: new El("div"), now: new El("div"), detail: new El("div"),
  state: new El("div"), play: new El("button"), "tab-fav": new El("button"),
  "search-form": new El("form"), q: new El("input"),
};

const STATIONS = [
  { uuid: "a", name: "Alpha FM", url: "http://x.test/a.mp3", codec: "MP3",
    bitrate: 128, tags: "jazz" },
  { uuid: "b", name: "Beta FM", url: "http://x.test/b.mp3", codec: "AAC",
    bitrate: 96, tags: "news" },
];
const fetched = [];
const reports = [];
const timers = [];

const sandbox = {
  console: console,
  document: {
    getElementById: function (id) { return ids[id]; },
    createElement: function (tag) { return new El(tag); },
  },
  fetch: function (url) {
    fetched.push(url);
    return Promise.resolve({
      ok: true,
      json: function () {
        return Promise.resolve(
          { kind: "favourites", source: "live", stations: STATIONS });
      },
    });
  },
  setTimeout: function (fn) { timers.push(fn); return timers.length; },
  clearTimeout: function (id) { if (id) { timers[id - 1] = null; } },
  localStorage: {
    getItem: function () { return null; },
    setItem: function () {},
  },
  // The app's half of the contract, recording rather than acting.
  RoamAudio: {
    onPlay: function () { reports.push("onPlay"); },
    onPause: function () { reports.push("onPause"); },
  },
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(source, sandbox, { filename: "radio.html" });

function runTimers() {
  const due = timers.slice();
  timers.length = 0;
  due.forEach(function (f) { if (f) { f(); } });
}

(async function () {
  const tick = function () { return new Promise(function (r) { setImmediate(r); }); };
  await tick(); await tick();

  assert(fetched.length === 1, "the page did not ask the hub for stations");
  assert(fetched[0].indexOf("/radio/stations") === 0, "asked for " + fetched[0]);
  const rows = ids.list.getElementsByClassName("station");
  assert(rows.length === 2, "expected two stations, drew " + rows.length);

  rows[0].click();
  assert(audio.src === STATIONS[0].url, "tapping a station did not open it");
  assert(reports.join(",") === "onPlay", "reported: " + reports.join(","));

  // The app takes the audio away -- PTT, or a call.
  sandbox.RoamRadio.pause();
  assert(audio.src === "", "an interruption must hang up, not merely pause");
  audio.fire("error");   // dropping src fires one of these
  assert(timers.length === 0, "a held stream must never schedule a retry");
  assert(reports.join(",") === "onPlay", "an interruption is not him pausing");

  // ...and gives it back.
  sandbox.RoamRadio.play(1);
  assert(audio.src === STATIONS[0].url, "the app gave the audio back and nothing resumed");
  assert(reports.join(",") === "onPlay", "resuming must not report again (it would loop)");

  // A genuinely dropped stream.
  audio.fire("error");
  assert(timers.length === 1, "a dropped stream must retry");
  audio.src = "";
  runTimers();
  assert(audio.src === STATIONS[0].url, "the retry did not re-open the stream");

  // He presses Stop.
  ids.play.click();
  assert(audio.src === "", "Stop must hang up");
  assert(reports.join(",") === "onPlay,onPause", "reported: " + reports.join(","));

  // Nothing may start playing that he did not ask for.
  sandbox.RoamRadio.play(1);
  assert(audio.src === "", "the app resumed music he had stopped");

  console.log("ok");
})();
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_player_obeys_him_and_the_app(tmp_path):
    """The whole player, minus the decoder, run in a browser-shaped sandbox.

    ⚠️ The four failures this is here for are all silent on the device: a
    station that opens nothing, a PTT interruption that the retry logic fights,
    a resume that reports itself and loops the app's focus handling, and a Stop
    that leaves the connection open.
    """
    driver = tmp_path / "drive.js"
    driver.write_text(DRIVER, encoding="utf-8")
    result = subprocess.run(
        ("node", str(driver), str(WEB_DIR / "radio.html")),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert result.stdout.strip().endswith("ok")
