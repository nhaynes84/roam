"""The Google Photos shared-album bridge.

Mocked at `urllib.request.urlopen`, with a synthetic share page shaped like the
real one: several `AF_initDataCallback` blocks, JavaScript object literals
around a JSON array, and the media items nested well below the root.

The rules under test, in order of how expensive they are to get wrong:

1. **No album configured -> do nothing, quietly.** That is the steady state
   until he creates it, and it must not write state or log noise.
2. **First run primes.** An 800-photo album must not become 800 files.
3. **Never raise.** Network down, page garbage, disk full: log and exit 0.
4. A `Content-Disposition` off the network can never become a path.
"""

from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path

import pytest

import photo_bridge as pb


# --------------------------------------------------------------- fake pages


def make_page(items: list[tuple[str, str, int]]) -> str:
    """A share page: config block, strings block, then the album block.

    `items` are (id, base_url, ts_ms). The nesting depth and the junk siblings
    are the point -- the parser must find items structurally, not by index.
    """
    album = [
        "AF1QipAlbumKey",
        [
            [item_id, [url, 4032, 3024], ts, None, ["ignored"], 0]
            for item_id, url, ts in items
        ],
        None,
        {"owner": "someone"},
    ]
    blocks = [
        "AF_initDataCallback({key: 'ds:0', hash: '1', data:[[\"config\",null,1]],"
        " sideChannel: {}});",
        "AF_initDataCallback({key: 'ds:2', hash: '3', data:"
        + json.dumps(["strings", "with ] a bracket", "and 'quotes'"])
        + ", sideChannel: {}});",
        "AF_initDataCallback({key: 'ds:5', hash: '9', data:"
        + json.dumps([None, album])
        + ", sideChannel: {}});",
    ]
    return (
        "<!doctype html><html><head><title>Album</title></head><body>"
        + "".join(f"<script nonce='abc'>{b}</script>" for b in blocks)
        + "</body></html>"
    )


def item(n: int, ts: int = 1_700_000_000_000) -> tuple[str, str, int]:
    return (
        f"AF1QipMediaId{n}",
        f"https://lh3.googleusercontent.com/pw/BASEURLTOKEN{n:04d}xxxxxxxxxxxxxxxxxxxx",
        ts + n * 1000,
    )


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, headers: dict[str, str] | None = None) -> None:
        super().__init__(body)
        self.headers = _Headers(headers or {})

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class _Headers(dict):
    def get_content_charset(self):
        return "utf-8"


@pytest.fixture
def paths(tmp_path, monkeypatch):
    """Config / state / inbox, all inside tmp_path."""
    monkeypatch.setattr(pb, "LOG_PATH", tmp_path / "photos.log")
    return {
        "config": tmp_path / "photo-album.txt",
        "state": tmp_path / "photo-state.json",
        "inbox": tmp_path / "inbox",
    }


def call(paths, **kw):
    return pb.run(
        config_path=paths["config"],
        state_path=paths["state"],
        inbox=paths["inbox"],
        **kw,
    )


@pytest.fixture
def network(monkeypatch):
    """Serve the album page and every media download from memory."""
    served = {"page": make_page([item(1), item(2)]), "downloads": [], "fail": None}

    def fake_urlopen(request, timeout=None):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        if served["fail"]:
            raise served["fail"]
        if "photos.google.com" in url or "goo.gl" in url:
            return FakeResponse(served["page"].encode("utf-8"))
        served["downloads"].append(url)
        return FakeResponse(
            b"\x89PNG\r\n\x1a\n" + b"pixels" * 100,
            {"Content-Type": "image/png"},
        )

    monkeypatch.setattr(pb.urllib.request, "urlopen", fake_urlopen)
    return served


ALBUM = "https://photos.google.com/share/AF1QipShareKey?key=abc123"


# ------------------------------------------------------------------- config


def test_no_config_file_does_nothing(paths, network):
    assert call(paths) == 0
    assert not paths["state"].exists()
    assert not paths["inbox"].exists()
    assert network["downloads"] == []


def test_empty_config_file_does_nothing(paths, network):
    paths["config"].write_text("\n\n", encoding="utf-8")
    assert call(paths) == 0
    assert not paths["state"].exists()


def test_comments_only_config_does_nothing(paths, network):
    paths["config"].write_text("# put the album link here\n", encoding="utf-8")
    assert call(paths) == 0
    assert not paths["state"].exists()


def test_reads_url_past_comments_and_blank_lines(tmp_path):
    path = tmp_path / "album.txt"
    path.write_text(f"# a comment\n\n{ALBUM}\n", encoding="utf-8")
    assert pb.read_album_url(path) == ALBUM


def test_unreadable_config_is_none(tmp_path):
    assert pb.read_album_url(tmp_path / "nope.txt") is None
    assert pb.read_album_url(tmp_path) is None  # a directory


# ------------------------------------------------------------------ parsing


def test_extracts_media_items_from_af_init_data():
    page = make_page([item(1), item(2), item(3)])
    found = pb.extract_media(page)
    assert [it.id for it in found] == [
        "AF1QipMediaId1",
        "AF1QipMediaId2",
        "AF1QipMediaId3",
    ]
    assert found[0].url.startswith("https://lh3.googleusercontent.com/pw/")
    assert found[0].ts_ms == 1_700_000_001_000


def test_download_url_asks_for_the_original():
    it = pb.MediaItem("id", "https://lh3.googleusercontent.com/pw/TOKEN")
    assert it.download_url.endswith("=d")
    # An existing size suffix is replaced, not appended to.
    sized = pb.MediaItem("id", "https://lh3.googleusercontent.com/pw/TOKEN=w530-h354-n")
    assert sized.download_url == "https://lh3.googleusercontent.com/pw/TOKEN=d"


def test_brackets_inside_strings_do_not_end_the_scan():
    payload = json.dumps([["a]b", "c[d"], ["ok"]])
    html = f"AF_initDataCallback({{key: 'ds:1', data:{payload}, sideChannel: {{}}}});"
    assert list(pb.iter_data_blocks(html)) == [[["a]b", "c[d"], ["ok"]]]


def test_avatars_and_ui_urls_are_not_media_items():
    """A profile picture is a googleusercontent URL too. Structure decides."""
    html = (
        "AF_initDataCallback({key: 'ds:1', data:"
        + json.dumps(
            [
                "https://lh3.googleusercontent.com/a/AVATAR=s64",
                ["some", "strings"],
                {"k": "https://lh3.googleusercontent.com/ui/SPRITE"},
            ]
        )
        + ", sideChannel: {}});"
    )
    assert pb.extract_media(html) == []


def test_falls_back_to_scraping_when_the_shape_changes():
    html = (
        "<html>no callbacks here, just "
        "https://lh3.googleusercontent.com/pw/AAAAAAAAAAAAAAAAAAAAAAAAAAAA "
        "in the markup</html>"
    )
    found = pb.extract_media(html)
    assert len(found) == 1
    assert found[0].url.endswith("AAAA")


def test_garbage_page_yields_nothing_without_raising():
    assert pb.extract_media("<html>totally empty</html>") == []
    assert pb.extract_media("AF_initDataCallback({data:[[[[") == []


def test_an_album_page_is_told_apart_from_a_login_wall():
    assert pb.looks_like_album_page(make_page([item(1)]))
    assert pb.looks_like_album_page(make_page([]))  # empty album, still an album
    assert not pb.looks_like_album_page("<html>sign in to continue</html>")


# ------------------------------------------------------------- short links


class FakeOpener:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@pytest.fixture
def opener(monkeypatch):
    """Swap the no-redirect opener `resolve_share_url` builds."""
    box = {}

    def install(response):
        box["opener"] = FakeOpener(response)
        monkeypatch.setattr(
            pb.urllib.request, "build_opener", lambda *a, **kw: box["opener"]
        )
        return box["opener"]

    return install


REAL_ALBUM = "https://photos.google.com/share/AF1QipReal?key=xyz"


def test_short_link_is_resolved_by_a_non_following_head(opener):
    """⚠️ A browser UA gets a 200 JS interstitial with no destination in it.
    HEAD, no redirects, plain UA -- that is the only shape that works."""
    fake = opener(FakeResponse(b"", {"Location": REAL_ALBUM}))
    assert pb.resolve_share_url("https://photos.app.goo.gl/abc123") == REAL_ALBUM
    request = fake.requests[0]
    assert request.get_method() == "HEAD"
    assert "Mozilla" not in request.headers.get("User-agent", "")


def test_short_link_resolves_from_a_302_raised_as_an_error(opener):
    err = urllib.error.HTTPError(
        "https://photos.app.goo.gl/abc123", 302, "Found", None, None
    )
    err.headers = _Headers({"Location": REAL_ALBUM})
    opener(err)
    assert pb.resolve_share_url("https://photos.app.goo.gl/abc123") == REAL_ALBUM


def test_a_long_link_is_left_alone(opener):
    fake = opener(FakeResponse(b"", {"Location": "https://evil.example/"}))
    assert pb.resolve_share_url(REAL_ALBUM) == REAL_ALBUM
    assert fake.requests == []  # no request made at all


def test_a_redirect_somewhere_else_is_not_followed(opener):
    opener(FakeResponse(b"", {"Location": "https://accounts.google.com/signin"}))
    short = "https://photos.app.goo.gl/abc123"
    assert pb.resolve_share_url(short) == short


def test_short_link_failure_degrades_to_the_url_we_have(opener):
    opener(urllib.error.URLError("dns"))
    short = "https://photos.app.goo.gl/abc123"
    assert pb.resolve_share_url(short) == short


# ------------------------------------------------------------- high water


def test_first_run_primes_and_downloads_nothing(paths, network):
    paths["config"].write_text(ALBUM + "\n", encoding="utf-8")
    assert call(paths) == 0
    assert network["downloads"] == []
    state = json.loads(paths["state"].read_text())
    assert state["primed"] is True
    assert set(state["seen"]) == {"AF1QipMediaId1", "AF1QipMediaId2"}
    assert not paths["inbox"].exists()


def test_second_run_takes_only_new_items(paths, network):
    paths["config"].write_text(ALBUM + "\n", encoding="utf-8")
    call(paths)  # prime
    network["page"] = make_page([item(1), item(2), item(3), item(4)])
    assert call(paths) == 2
    assert len(network["downloads"]) == 2
    assert all(url.endswith("=d") for url in network["downloads"])
    assert len(list(paths["inbox"].iterdir())) == 2
    # And a third run with nothing new is a no-op.
    assert call(paths) == 0
    assert len(network["downloads"]) == 2


def test_a_deleted_inbox_file_is_not_re_downloaded(paths, network):
    """The mark is the album, not the directory -- he moves these files away."""
    paths["config"].write_text(ALBUM + "\n", encoding="utf-8")
    call(paths)
    network["page"] = make_page([item(1), item(2), item(3)])
    call(paths)
    for f in paths["inbox"].iterdir():
        f.unlink()
    assert call(paths) == 0


def test_a_run_is_capped_and_the_rest_come_next_time(paths, network):
    paths["config"].write_text(ALBUM + "\n", encoding="utf-8")
    call(paths)
    network["page"] = make_page([item(n) for n in range(1, 10)])
    assert call(paths, max_items=3) == 3
    assert call(paths, max_items=3) == 3
    assert call(paths, max_items=3) == 1


def test_a_failed_download_is_retried_next_run(paths, network, monkeypatch):
    paths["config"].write_text(ALBUM + "\n", encoding="utf-8")
    call(paths)
    network["page"] = make_page([item(1), item(2), item(3)])
    monkeypatch.setattr(pb, "download", lambda *a, **kw: None)
    assert call(paths) == 0
    state = json.loads(paths["state"].read_text())
    assert "AF1QipMediaId3" not in state["seen"]


# -------------------------------------------------------------- robustness


def test_network_failure_is_silent_and_leaves_the_mark_alone(paths, network):
    paths["config"].write_text(ALBUM + "\n", encoding="utf-8")
    call(paths)
    before = paths["state"].read_text()
    network["fail"] = urllib.error.URLError("no route to host")
    assert call(paths) == 0
    assert paths["state"].read_text() == before


def test_timeout_before_the_first_run_writes_no_state(paths, network):
    paths["config"].write_text(ALBUM + "\n", encoding="utf-8")
    network["fail"] = OSError("timed out")
    assert call(paths) == 0
    assert not paths["state"].exists()


def test_a_login_wall_does_not_prime(paths, network):
    """Priming on a page we failed to read would silently skip real photos."""
    paths["config"].write_text(ALBUM + "\n", encoding="utf-8")
    network["page"] = "<html>login required</html>"
    assert call(paths) == 0
    assert not paths["state"].exists()


def test_an_empty_album_is_normal_and_still_primes(paths, network):
    """He may share the album before putting anything in it. The first photo
    he then adds must arrive -- which it only does if the mark exists."""
    paths["config"].write_text(ALBUM + "\n", encoding="utf-8")
    network["page"] = make_page([])
    assert call(paths) == 0
    state = json.loads(paths["state"].read_text())
    assert state["primed"] is True and state["seen"] == []
    network["page"] = make_page([item(1)])
    assert call(paths) == 1


def test_corrupt_state_file_is_survivable(paths, network):
    paths["config"].write_text(ALBUM + "\n", encoding="utf-8")
    paths["state"].write_text("{not json", encoding="utf-8")
    assert call(paths) == 0  # re-primes rather than dying
    assert json.loads(paths["state"].read_text())["primed"] is True


def test_main_returns_zero_even_when_run_explodes(monkeypatch, tmp_path):
    monkeypatch.setattr(pb, "LOG_PATH", tmp_path / "photos.log")
    monkeypatch.setattr(pb, "run", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert pb.main([]) == 0


# ---------------------------------------------------------------- filenames


@pytest.mark.parametrize(
    "disposition, expected",
    [
        ('attachment; filename="IMG_4021.jpg"', "IMG_4021.jpg"),
        ('attachment; filename="../../.ssh/authorized_keys"', "authorized_keys"),
        ('attachment; filename="/etc/passwd"', "passwd"),
        ('attachment; filename="..%2f..%2fevil.png"', "_2f.._2fevil.png"),
        ("attachment; filename*=UTF-8''holiday%20snap.jpg", "holiday_20snap.jpg"),
    ],
)
def test_content_disposition_can_never_be_a_path(disposition, expected):
    headers = _Headers({"Content-Disposition": disposition, "Content-Type": "image/jpeg"})
    name = pb._filename_for(pb.MediaItem("id", "https://x/y"), headers)
    assert name == expected
    assert "/" not in name and not name.startswith(".")


def test_filename_falls_back_to_content_type():
    headers = _Headers({"Content-Type": "video/mp4"})
    name = pb._filename_for(pb.MediaItem("AF1QipMediaId9", "https://x/y"), headers)
    assert name.endswith(".mp4") and name.startswith("photo-")


def test_downloads_never_overwrite_an_existing_file(tmp_path, network):
    (tmp_path).mkdir(exist_ok=True)
    first = pb.download(pb.MediaItem("a", "https://lh3.googleusercontent.com/pw/A"), tmp_path)
    second = pb.download(pb.MediaItem("b", "https://lh3.googleusercontent.com/pw/B"), tmp_path)
    assert first is not None and second is not None
    assert first != second
    assert first.exists() and second.exists()


def test_partial_downloads_are_not_left_in_the_inbox(tmp_path, monkeypatch, network):
    class Broken(FakeResponse):
        def read(self, n=-1):
            raise OSError("connection reset")

    monkeypatch.setattr(
        pb.urllib.request,
        "urlopen",
        lambda req, timeout=None: Broken(b"", {"Content-Type": "image/png"}),
    )
    assert pb.download(pb.MediaItem("a", "https://lh3.googleusercontent.com/pw/A"), tmp_path) is None
    assert list(tmp_path.iterdir()) == []


def test_oversized_downloads_are_dropped(tmp_path, network, monkeypatch):
    monkeypatch.setattr(pb, "MAX_BYTES", 16)
    assert pb.download(pb.MediaItem("a", "https://lh3.googleusercontent.com/pw/A"), tmp_path) is None
    assert list(tmp_path.iterdir()) == []
