"""The file browser, the share button and the STL viewer.

Most of this file is one question asked many ways: **can a request get out of
the two shared folders?** `files.resolve` is the only thing standing between a
query string and the filesystem, so it is tested against `..` in both slash
directions, absolute paths, nul bytes, sibling directories with a prefix name,
and -- the one a lexical check always misses -- a **symlink inside a shared
folder pointing somewhere else entirely**.

The rest covers the parts that would fail on the actual client: the pages must
parse as 2019 JavaScript, because the Pixel 1 runs Chrome 74 and cannot be
updated, and a filename must not be able to end a `<script>` block.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import files as files_mod
import hub as hub_mod
from conftest import TOKEN

HUB_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = HUB_DIR / "web"


@pytest.fixture
def collab(tmp_path) -> dict[str, Path]:
    """A miniature ~/Collab, plus a secret outside it to try to reach."""
    cad = tmp_path / "Collab" / "CAD"
    photos = tmp_path / "Collab" / "Photos"
    (cad / "roam-touch" / "archive").mkdir(parents=True)
    photos.mkdir(parents=True)

    (cad / "roam-touch" / "bracer.step").write_bytes(b"ISO-10303-21;\n")
    (cad / "roam-touch" / "bracer.stl").write_bytes(b"solid x\nendsolid x\n")
    (cad / "roam-touch" / "orphan.step").write_bytes(b"ISO-10303-21;\n")
    (cad / "roam-touch" / "archive" / "old.stl").write_bytes(b"solid old\n")
    (cad / ".DS_Store").write_bytes(b"junk")
    (photos / "shot.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"jpegbytes" * 20)

    secret = tmp_path / "secrets"
    secret.mkdir()
    (secret / "id_rsa").write_text("PRIVATE KEY", encoding="utf-8")
    # A directory whose name merely starts with a root's name. A `startswith`
    # containment check would let this through.
    sibling = tmp_path / "Collab" / "CAD-private"
    sibling.mkdir()
    (sibling / "salary.txt").write_text("nope", encoding="utf-8")

    return {"cad": cad, "photos": photos, "secret": secret, "root": tmp_path}


@pytest.fixture
def roots(collab) -> dict[str, Path]:
    return {"CAD": collab["cad"], "Photos": collab["photos"]}


@pytest.fixture
def fs_client(collab, tmp_path, store, fake_tmux):
    settings = hub_mod.Settings(
        token=TOKEN,
        db_path=tmp_path / "hub.sqlite",
        token_file=tmp_path / "token.txt",
        poll_interval=0.05,
        collab_cad=collab["cad"],
        collab_photos=collab["photos"],
        inbox=tmp_path / "inbox",
        thumb_cache=tmp_path / "thumbs",
    )
    app = hub_mod.create_app(settings=settings, store=store)
    with TestClient(app) as c:
        c.inbox = tmp_path / "inbox"
        yield c


# ------------------------------------------------------------------ listing


def test_empty_path_lists_the_roots(fs_client, auth):
    body = fs_client.get("/files", headers=auth).json()
    assert [e["name"] for e in body["entries"]] == ["CAD", "Photos"]
    assert body["parent"] is None


def test_listing_marks_kinds_and_hides_dotfiles(fs_client, auth):
    body = fs_client.get("/files", params={"path": "CAD/roam-touch"}, headers=auth).json()
    kinds = {e["name"]: e["kind"] for e in body["entries"]}
    assert kinds == {
        "archive": "dir",
        "bracer.step": "cad",
        "bracer.stl": "mesh",
        "orphan.step": "cad",
    }
    # Directories first, then case-insensitive name order.
    assert [e["name"] for e in body["entries"]][0] == "archive"
    assert body["parent"] == "CAD"
    assert ".DS_Store" not in json.dumps(body)


def test_a_step_advertises_the_stl_beside_it(fs_client, auth):
    """The build pipeline drops foo.stl next to foo.step; say so, so the
    client can offer 3D on a file it could never render itself."""
    body = fs_client.get("/files", params={"path": "CAD/roam-touch"}, headers=auth).json()
    entries = {e["name"]: e for e in body["entries"]}
    assert entries["bracer.step"]["mesh_path"] == "CAD/roam-touch/bracer.stl"
    assert "mesh_path" not in entries["orphan.step"]


def test_a_missing_root_is_listed_but_flagged(tmp_path, roots):
    roots = dict(roots, Photos=tmp_path / "not-there")
    body = files_mod.listdir("", roots)
    flags = {e["name"]: e.get("missing") for e in body["entries"]}
    assert flags == {"CAD": False, "Photos": True}


# ---------------------------------------------------------------- traversal


ESCAPES = [
    "CAD/../../secrets/id_rsa",
    "CAD/../..",
    "CAD/roam-touch/../../../secrets/id_rsa",
    "CAD\\..\\..\\secrets",           # the other slash
    "CAD/./../secrets",
    "..",
    "../secrets",
    "CAD/roam-touch/..\\..\\..\\secrets",
]

#: Reaches the resolver as one literal segment rather than as `..`, because
#: nothing here percent-decodes -- FastAPI already did that once, and doing it
#: again is precisely the double-decoding bug this shape is fishing for. It has
#: to end up *inside* a root and simply not exist, never outside one.
ENCODED = ["CAD/..%2f..%2fsecrets", "CAD/%2e%2e/%2e%2e/secrets"]


@pytest.mark.parametrize("path", ESCAPES)
def test_traversal_is_refused_by_the_resolver(path, roots):
    with pytest.raises(files_mod.BrowseError):
        files_mod.resolve(path, roots)


@pytest.mark.parametrize("path", ENCODED)
def test_percent_encoded_dots_stay_inside_the_root(path, roots, collab):
    """★ Not decoded a second time. The segment is a (nonexistent) filename."""
    _root, target = files_mod.resolve(path, roots)
    base = Path(os.path.realpath(collab["cad"]))
    assert base in target.parents
    with pytest.raises(files_mod.NotFound):
        files_mod.resolve_file(path, roots)


@pytest.mark.parametrize("path", ESCAPES + ENCODED)
@pytest.mark.parametrize("endpoint", ["/files", "/files/raw", "/files/thumb"])
def test_traversal_is_refused_by_every_endpoint(fs_client, auth, endpoint, path):
    response = fs_client.get(endpoint, params={"path": path}, headers=auth)
    assert response.status_code in (400, 404), response.text
    assert "PRIVATE KEY" not in response.text


@pytest.mark.parametrize("path", ESCAPES + ENCODED)
def test_traversal_is_refused_by_share(fs_client, auth, path):
    response = fs_client.post("/share", json={"path": path}, headers=auth)
    assert response.status_code in (400, 404), response.text
    assert not list((fs_client.inbox).iterdir()) if fs_client.inbox.exists() else True


def test_an_absolute_path_is_not_a_root(fs_client, auth, collab):
    response = fs_client.get(
        "/files/raw", params={"path": str(collab["secret"] / "id_rsa")}, headers=auth
    )
    assert response.status_code == 404
    assert "PRIVATE KEY" not in response.text


def test_a_nul_byte_is_refused(fs_client, auth, roots):
    with pytest.raises(files_mod.BrowseError):
        files_mod.resolve("CAD/\x00etc", roots)


def test_a_sibling_directory_with_a_prefix_name_is_not_inside(fs_client, auth, roots):
    """`/Collab/CAD-private` starts with `/Collab/CAD`. Component containment,
    not string containment, is what keeps it out."""
    with pytest.raises(files_mod.NotFound):
        files_mod.resolve("CAD-private/salary.txt", roots)
    response = fs_client.get(
        "/files", params={"path": "CAD-private/salary.txt"}, headers=auth
    )
    assert response.status_code == 404


def test_a_symlink_out_of_the_tree_is_refused(fs_client, auth, collab, roots):
    """★ The one a lexical `..` check always misses. `CAD/shortcut` is a
    perfectly ordinary directory entry that happens to be somewhere else."""
    link = collab["cad"] / "shortcut"
    link.symlink_to(collab["secret"])
    with pytest.raises(files_mod.BrowseError):
        files_mod.resolve("CAD/shortcut/id_rsa", roots)
    response = fs_client.get(
        "/files/raw", params={"path": "CAD/shortcut/id_rsa"}, headers=auth
    )
    assert response.status_code == 400
    assert "PRIVATE KEY" not in response.text


def test_a_symlink_that_stays_inside_is_fine(collab, roots):
    link = collab["cad"] / "latest"
    link.symlink_to(collab["cad"] / "roam-touch")
    _root, target = files_mod.resolve("CAD/latest/bracer.stl", roots)
    assert target == Path(os.path.realpath(collab["cad"] / "roam-touch" / "bracer.stl"))


def test_a_directory_is_not_a_file_and_a_file_is_not_a_directory(fs_client, auth):
    assert fs_client.get(
        "/files/raw", params={"path": "CAD/roam-touch"}, headers=auth
    ).status_code == 404
    assert fs_client.get(
        "/files", params={"path": "CAD/roam-touch/bracer.stl"}, headers=auth
    ).status_code == 404


# --------------------------------------------------------------------- auth


@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/files"),
        ("get", "/files/raw"),
        ("get", "/files/thumb"),
        ("get", "/browse"),
        ("get", "/view/stl"),
        ("post", "/share"),
    ],
)
def test_every_file_endpoint_needs_the_token(fs_client, method, path):
    call = getattr(fs_client, method)
    kwargs = {"json": {"path": "CAD"}} if method == "post" else {}
    assert call(path, params={"path": "CAD"}, **kwargs).status_code == 401


def test_a_query_token_works_because_an_img_tag_cannot_send_a_header(fs_client):
    """Same concession /ws already makes, for the same reason."""
    response = fs_client.get(
        "/files/raw", params={"path": "Photos/shot.jpg", "token": TOKEN}
    )
    assert response.status_code == 200


def test_a_wrong_query_token_is_still_401(fs_client):
    response = fs_client.get(
        "/files", params={"path": "CAD", "token": "not-the-token"}
    )
    assert response.status_code == 401


# ---------------------------------------------------------------- raw/thumb


def test_raw_serves_the_bytes_inline(fs_client, auth):
    response = fs_client.get(
        "/files/raw", params={"path": "Photos/shot.jpg"}, headers=auth
    )
    assert response.status_code == 200
    assert response.content.startswith(b"\xff\xd8\xff")
    assert "inline" in response.headers["content-disposition"]


def test_thumb_always_returns_an_image_even_without_sips(fs_client, auth, monkeypatch):
    monkeypatch.setattr(files_mod, "thumbnail", lambda *a, **kw: None)
    response = fs_client.get(
        "/files/thumb", params={"path": "Photos/shot.jpg"}, headers=auth
    )
    assert response.status_code == 200 and response.content


def test_thumbnail_declines_non_images(tmp_path, collab):
    assert files_mod.thumbnail(collab["cad"] / "roam-touch" / "bracer.stl",
                               cache_dir=tmp_path) is None


@pytest.mark.skipif(shutil.which("sips") is None, reason="sips is macOS-only")
def test_thumbnail_shrinks_a_real_image(tmp_path, collab):
    """Uses the actual `sips` on this box -- the fake JPEG above is not a real
    image, so a real one is generated first."""
    source = collab["photos"] / "real.png"
    made = subprocess.run(
        ("sips", "-s", "format", "png", "--resampleWidth", "800",
         "/System/Library/CoreServices/DefaultDesktop.heic", "--out", str(source)),
        capture_output=True,
    )
    if made.returncode != 0 or not source.exists():
        pytest.skip("no sample image on this box")
    small = files_mod.thumbnail(source, max_px=64, cache_dir=tmp_path)
    assert small is not None and small.stat().st_size < source.stat().st_size
    # Second call is the cache, not another sips run.
    assert files_mod.thumbnail(source, max_px=64, cache_dir=tmp_path) == small


# -------------------------------------------------------------------- share


def test_share_copies_into_the_inbox(fs_client, auth, collab):
    response = fs_client.post(
        "/share", json={"path": "CAD/roam-touch/bracer.stl"}, headers=auth
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "bracer.stl"
    landed = fs_client.inbox / "bracer.stl"
    assert landed.read_bytes() == (collab["cad"] / "roam-touch" / "bracer.stl").read_bytes()
    # Copy, never move: the shared folder is his.
    assert (collab["cad"] / "roam-touch" / "bracer.stl").exists()


def test_sharing_twice_does_not_clobber(fs_client, auth):
    fs_client.post("/share", json={"path": "CAD/roam-touch/bracer.stl"}, headers=auth)
    second = fs_client.post(
        "/share", json={"path": "CAD/roam-touch/bracer.stl"}, headers=auth
    ).json()
    assert second["name"] != "bracer.stl"
    assert len(list(fs_client.inbox.iterdir())) == 2


def test_share_leaves_no_part_file_behind(fs_client, auth):
    fs_client.post("/share", json={"path": "Photos/shot.jpg"}, headers=auth)
    assert not [p for p in fs_client.inbox.iterdir() if p.name.endswith(".part")]


def test_sharing_a_directory_is_refused(fs_client, auth):
    response = fs_client.post("/share", json={"path": "CAD/roam-touch"}, headers=auth)
    assert response.status_code == 404
    assert not fs_client.inbox.exists() or not list(fs_client.inbox.iterdir())


def test_a_huge_file_is_not_shared(tmp_path, roots, collab):
    big = collab["cad"] / "huge.stl"
    big.write_bytes(b"x" * 4096)
    with pytest.raises(files_mod.BrowseError):
        files_mod.share("CAD/huge.stl", roots, inbox=tmp_path / "inbox", max_bytes=1024)
    assert not (tmp_path / "inbox" / "huge.stl").exists()


# --------------------------------------------------------------- the pages


def test_browse_page_carries_the_token_and_no_referrer(fs_client, auth):
    response = fs_client.get("/browse", headers=auth)
    assert response.status_code == 200
    assert TOKEN in response.text
    assert "__ROAM_TOKEN__" not in response.text
    assert response.headers["referrer-policy"] == "no-referrer"


def test_stl_viewer_renders_only_stl(fs_client, auth):
    ok = fs_client.get(
        "/view/stl", params={"path": "CAD/roam-touch/bracer.stl"}, headers=auth
    )
    assert ok.status_code == 200
    assert "CAD/roam-touch/bracer.stl" in ok.text
    # ⚠️ .step needs an OCCT-class kernel. Refuse it here rather than shipping a
    # viewer that loads, spins, and fails.
    refused = fs_client.get(
        "/view/stl", params={"path": "CAD/roam-touch/bracer.step"}, headers=auth
    )
    assert refused.status_code == 415


def test_stl_viewer_404s_a_missing_model(fs_client, auth):
    response = fs_client.get(
        "/view/stl", params={"path": "CAD/roam-touch/nope.stl"}, headers=auth
    )
    assert response.status_code == 404


def test_a_filename_cannot_break_out_of_the_script_block(fs_client, auth, collab):
    """A path is templated into a JS string literal, so a filename full of
    markup must come out inert.

    (A POSIX filename cannot contain `/`, so the exact string `</script>` can
    never arrive this way — but `<`, `>`, `"` and `&` all can, and escaping
    those is the same defence. `_js_literal` is tested on `</script>` directly
    below, where it *can* be constructed.)
    """
    nasty = collab["cad"] / '<img src=x onerror="alert(1)">&.stl'
    nasty.write_bytes(b"solid x\n")
    response = fs_client.get(
        "/view/stl", params={"path": "CAD/" + nasty.name}, headers=auth
    )
    assert response.status_code == 200
    assert "<img src=x" not in response.text
    assert 'onerror="alert(1)"' not in response.text
    assert "\\u003cimg src=x onerror=\\\"alert(1)\\\"\\u003e\\u0026" in response.text


def test_js_literal_escapes_the_dangerous_shapes():
    assert hub_mod._js_literal('a"b') == '"a\\"b"'
    assert "<" not in hub_mod._js_literal("</script>")
    assert hub_mod._js_literal("\u2028") == '"\\u2028"'


def test_vendor_assets_are_an_allow_list(fs_client):
    assert fs_client.get("/web/vendor/three.min.js").status_code == 200
    for bad in ("browse.html", "..%2f..%2fhub.py", "hub.py"):
        assert fs_client.get("/web/vendor/" + bad).status_code == 404


# ------------------------------------------------- the 2019 browser contract


JS_PATHS = [
    WEB_DIR / "vendor" / "three.min.js",
    WEB_DIR / "vendor" / "STLLoader.js",
    WEB_DIR / "vendor" / "OrbitControls.js",
]

#: Syntax Chrome 74 cannot parse. `?.` and `??` are Chrome 80; class fields and
#: `#private` are later still. A page using any of them is a blank screen on
#: his wrist, not a degraded one -- the whole script block fails to parse.
FORBIDDEN = [
    (r"\?\?", "nullish coalescing (Chrome 80)"),
    (r"\?\.[A-Za-z_$\[(]", "optional chaining (Chrome 80)"),
    (r"^\s*#[A-Za-z_$][\w$]*\s*[=;(]", "private class field (Chrome 74 has none)"),
    (r"\bcatch\s*\{", "optional catch binding without parens"),
]

#: CSS the engine does not understand. `gap` inside flexbox is the sneaky one:
#: it is Chrome 84, silently ignored before that, and the layout just collapses.
FORBIDDEN_CSS = [
    (r":has\(", ":has() (Chrome 105)"),
    (r"@container", "container queries (Chrome 105)"),
    (r"^\s*gap\s*:", "flex/grid `gap` shorthand (Chrome 84) -- use grid-gap"),
]


def inline_scripts(html: str) -> str:
    return "\n".join(re.findall(r"<script>(.*?)</script>", html, re.S))


@pytest.mark.parametrize("page", ["browse.html", "stl.html"])
def test_our_pages_use_no_syntax_chrome_74_cannot_parse(page):
    source = inline_scripts((WEB_DIR / page).read_text(encoding="utf-8"))
    assert source.strip(), f"{page} has no inline script -- did the markup change?"
    for pattern, why in FORBIDDEN:
        found = re.search(pattern, source, re.M)
        assert not found, f"{page}: {why} at {found.start() if found else 0}"


@pytest.mark.parametrize("page", ["browse.html", "stl.html"])
def test_our_pages_use_no_css_chrome_74_cannot_parse(page):
    css = "\n".join(
        re.findall(r"<style>(.*?)</style>", (WEB_DIR / page).read_text("utf-8"), re.S)
    )
    for pattern, why in FORBIDDEN_CSS:
        found = re.search(pattern, css, re.M)
        assert not found, f"{page}: {why}"


def test_three_js_is_the_pinned_2020_build():
    """r112 is pinned, not stale: modern three.js is ES2020 modules that this
    engine cannot parse at all. See web/vendor/README.md before bumping."""
    header = JS_PATHS[0].read_text(encoding="utf-8", errors="replace")[:400]
    assert "threejs.org/license" in header
    for path in JS_PATHS:
        assert path.stat().st_size > 1000, path


def _acorn_available() -> bool:
    if shutil.which("node") is None:
        return False
    probe = subprocess.run(
        ("node", "-e", "require.resolve('acorn')"), capture_output=True
    )
    return probe.returncode == 0


@pytest.mark.skipif(
    not _acorn_available(),
    reason="node+acorn not installed here; `npm i acorn` somewhere and run with "
    "NODE_PATH=<that>/node_modules to turn this on",
)
@pytest.mark.parametrize("page", ["browse.html", "stl.html"])
def test_pages_really_parse_at_ecmaversion_2019(tmp_path, page):
    """The real check, when the tooling is on the box.

    ⚠️ Not esbuild `--target=chrome74`: esbuild *lowers* `?.` and `??` to
    compatible output instead of rejecting them, so it proves nothing about the
    source. Acorn pinned at ecmaVersion 2019 actually refuses them.
    """
    js = tmp_path / "page.js"
    js.write_text(inline_scripts((WEB_DIR / page).read_text("utf-8")), encoding="utf-8")
    script = (
        "const acorn=require('acorn'),fs=require('fs');"
        "acorn.parse(fs.readFileSync(process.argv[1],'utf8'),"
        "{ecmaVersion:2019,sourceType:'script'});"
    )
    result = subprocess.run(
        ("node", "-e", script, str(js)), capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
