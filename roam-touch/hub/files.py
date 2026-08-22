"""Browsing the collaboration folders, and handing a file to Claude.

Two directories are shared with the wrist: `~/Collab/CAD` and `~/Collab/Photos`.
They are **read-only** to the hub -- nothing here writes, renames or deletes
inside them. The one write it does is a *copy out*, into
`~/.claude/dropzone/inbox/`, which is how a browsed file reaches Claude by
exactly the same path a shared-album photo does (see `photo_bridge.py` and the
inbox contract in `README.md`). One delivery route, one place for it to break.

★ **The whole security surface of this module is `resolve`.** Everything else
takes an already-resolved path. A browse path is `<root>/<relative>` --
`CAD/estack/drum_lh.step` -- and a request that does not land strictly inside a
declared root is refused, whether it tried to get out with `..`, with an
absolute path, or through a **symlink pointing somewhere else entirely**. That
last one is why containment is checked *after* `Path.resolve()` and not before:
`~/Collab/CAD/shortcut -> /Users/talos/.ssh` is a perfectly ordinary-looking
directory entry, and lexical checks wave it straight through.

Kept out of `hub.py` deliberately: this is the part that has to be tested
adversarially, and a plain function taking a string is far easier to point a
hundred nasty inputs at than a route is.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Iterable

#: The shared folders, by the name they are browsed under.
DEFAULT_ROOTS: dict[str, Path] = {
    "CAD": Path.home() / "Collab" / "CAD",
    "Photos": Path.home() / "Collab" / "Photos",
}

#: Where a shared file is handed to Claude. See README.md, "the inbox contract".
DEFAULT_INBOX = Path.home() / ".claude" / "dropzone" / "inbox"

DEFAULT_THUMB_CACHE = Path.home() / "Library" / "Caches" / "roam-hub" / "thumbs"

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".bmp", ".tiff"}
#: ⚠️ **Render STL only.** The CAD folders are full of `.step`, which is a
#: boundary-representation format needing a real kernel (OCCT) to tessellate --
#: not something to attempt in a 2019 phone browser. The build pipeline emits
#: an `.stl` next to each one; the browser points at that instead.
MESH_EXTS = {".stl"}
#: Recognised, listed, downloadable -- but never rendered.
CAD_EXTS = {".step", ".stp", ".3mf", ".obj", ".scad", ".f3d", ".iges", ".igs"}

#: A file bigger than this is not something to hand a language model.
MAX_SHARE_BYTES = 64 * 1024 * 1024
#: Directories with thousands of entries would make a useless page anyway.
MAX_ENTRIES = 2000
THUMB_TIMEOUT_S = 15.0


class BrowseError(ValueError):
    """A path that is not allowed. The message is safe to show a client."""


class NotFound(BrowseError):
    """A well-formed path to something that is not there.

    Split from `BrowseError` so the API can answer 404 for a typo and 400 for
    an attempt to leave the shared folders -- "no such file" and "stop that"
    are different answers and should not share a status code.
    """


def _clean_segments(rel: str) -> list[str]:
    if "\x00" in rel:
        raise BrowseError("nul byte in path")
    # Both separators, because a client on any platform may send either and
    # `..\..\x` must not survive by being spelled with the other slash.
    normalised = rel.replace("\\", "/")
    segments = [s for s in normalised.split("/") if s not in ("", ".")]
    if any(s == ".." for s in segments):
        raise BrowseError("path traversal")
    return segments


def root_names(roots: dict[str, Path] | None = None) -> list[str]:
    return sorted((roots or DEFAULT_ROOTS).keys())


def resolve(rel: str, roots: dict[str, Path] | None = None) -> tuple[str, Path]:
    """A browse path -> `(root_name, absolute_path)`, or raise `BrowseError`.

    The containment check is `os.path.realpath` on both sides and then a
    prefix test on *path components*, which is the whole point: a string
    `startswith` would happily accept `/Users/talos/Collab/CAD-private` as
    being inside `/Users/talos/Collab/CAD`.
    """
    roots = roots or DEFAULT_ROOTS
    segments = _clean_segments(rel or "")
    if not segments:
        raise BrowseError("no root in path")
    name, rest = segments[0], segments[1:]
    base_raw = roots.get(name)
    if base_raw is None:
        raise NotFound(f"no such root: {name!r}")
    base = Path(os.path.realpath(base_raw))
    target = Path(os.path.realpath(base.joinpath(*rest))) if rest else base
    if target != base and base not in target.parents:
        # Reached only through a symlink out of the tree, or a root that is
        # itself a link. Either way it is not ours to serve.
        raise BrowseError("path escapes the shared folder")
    return name, target


def browse_path(root: str, target: Path, roots: dict[str, Path] | None = None) -> str:
    """The inverse of `resolve`: what a client should ask for next."""
    base = Path(os.path.realpath((roots or DEFAULT_ROOTS)[root]))
    if target == base:
        return root
    return root + "/" + str(target.relative_to(base)).replace(os.sep, "/")


def classify(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in MESH_EXTS:
        return "mesh"
    if ext in CAD_EXTS:
        return "cad"
    return "file"


def _entry(path: Path, root: str, roots: dict[str, Path]) -> dict[str, Any] | None:
    try:
        st = path.stat()
    except OSError:
        return None  # a broken symlink, or something that vanished mid-listing
    is_dir = path.is_dir()
    kind = "dir" if is_dir else classify(path)
    entry: dict[str, Any] = {
        "name": path.name,
        "path": browse_path(root, path, roots),
        "kind": kind,
        "size": 0 if is_dir else st.st_size,
        "mtime": st.st_mtime,
    }
    if kind == "cad":
        # ★ The build pipeline drops `foo.stl` beside `foo.step`. Saying so here
        # turns "I can't show you this" into "here is the mesh of it" without
        # the client having to guess the convention.
        mesh = path.with_suffix(".stl")
        if mesh.is_file():
            entry["mesh_path"] = browse_path(root, mesh, roots)
    return entry


def listdir(rel: str, roots: dict[str, Path] | None = None) -> dict[str, Any]:
    """One directory, or the list of roots when `rel` is empty.

    Dot-files are skipped: `.DS_Store` in every folder is noise, and nothing
    below a shared folder that starts with a dot was put there to be shared.
    """
    roots = roots or DEFAULT_ROOTS
    if not _clean_segments(rel or ""):
        entries = []
        for name in root_names(roots):
            base = roots[name]
            entry = {
                "name": name,
                "path": name,
                "kind": "dir",
                "size": 0,
                "mtime": base.stat().st_mtime if base.exists() else 0.0,
                "missing": not base.is_dir(),
            }
            entries.append(entry)
        return {"path": "", "parent": None, "entries": entries}

    root, target = resolve(rel, roots)
    if not target.is_dir():
        raise NotFound(f"not a directory: {rel}")
    entries: list[dict[str, Any]] = []
    try:
        children: Iterable[Path] = sorted(target.iterdir())
    except OSError as exc:
        raise NotFound(f"cannot read directory: {exc}") from exc
    for child in children:
        if child.name.startswith("."):
            continue
        entry = _entry(child, root, roots)
        if entry is not None:
            entries.append(entry)
        if len(entries) >= MAX_ENTRIES:
            break
    entries.sort(key=lambda e: (e["kind"] != "dir", e["name"].lower()))
    current = browse_path(root, target, roots)
    parent = current.rsplit("/", 1)[0] if "/" in current else ""
    return {"path": current, "parent": parent, "entries": entries}


def resolve_file(rel: str, roots: dict[str, Path] | None = None) -> Path:
    """A path that is definitely a regular file inside a root.

    `is_file()` rather than "exists and is not a directory", so a fifo or a
    device node cannot be handed to a `FileResponse` that would then block
    forever serving it.
    """
    _root, target = resolve(rel, roots)
    if not target.is_file():
        raise NotFound(f"not a file: {rel}")
    return target


# ------------------------------------------------------------------ sharing


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


def share(
    rel: str,
    roots: dict[str, Path] | None = None,
    inbox: Path = DEFAULT_INBOX,
    max_bytes: int = MAX_SHARE_BYTES,
) -> Path:
    """Copy a browsed file into the inbox. Returns where it landed.

    Copy, never move: the shared folders are his, and a browser tap must not be
    able to take a file out of them. Written as `.part` and renamed, per the
    inbox contract -- the prompt hook must never see a half-copied file.
    """
    source = resolve_file(rel, roots)
    size = source.stat().st_size
    if size > max_bytes:
        raise BrowseError(f"file is too large to share ({size} bytes)")
    inbox.mkdir(parents=True, exist_ok=True)
    target = _unique(inbox, source.name)
    part = target.with_name(target.name + ".part")
    try:
        shutil.copyfile(source, part)
        part.replace(target)
    except OSError:
        try:
            part.unlink()
        except OSError:
            pass
        raise
    return target


def deposit(
    name: str,
    data: bytes,
    inbox: Path = DEFAULT_INBOX,
    max_bytes: int = MAX_SHARE_BYTES,
) -> Path:
    """Put BYTES from a client into the inbox. Returns where they landed.

    ★ `share` above can only hand over a file that is already on talos, inside the
    shared folders. That is useless for "here is a photo from my laptop" -- the file
    is on the laptop. This is the same door, opened from the other side, so an
    attachment does not have to go via Google Photos or a screenshot.

    ⚠️ The name is taken as a SUGGESTION and reduced to its basename. A client is
    not trusted to pick a path: "../../.zshrc" must land as ".zshrc" in the inbox
    and nowhere else. Same `.part`-then-rename as `share`, per the inbox contract --
    the prompt hook must never see a half-written file.
    """
    if len(data) > max_bytes:
        raise BrowseError(f"file is too large to share ({len(data)} bytes)")
    if not data:
        raise BrowseError("refusing to share an empty file")
    # basename only, and never a dotfile-escape or an empty stem
    safe = os.path.basename(name).strip().lstrip(".") or "attachment"
    safe = safe.replace("/", "_").replace("\\", "_")[:120]
    inbox.mkdir(parents=True, exist_ok=True)
    target = _unique(inbox, safe)
    part = target.with_name(target.name + ".part")
    try:
        part.write_bytes(data)
        part.replace(target)
    except OSError:
        try:
            part.unlink()
        except OSError:
            pass
        raise
    return target


# --------------------------------------------------------------- thumbnails


def thumbnail(
    path: Path,
    max_px: int = 320,
    cache_dir: Path = DEFAULT_THUMB_CACHE,
) -> Path | None:
    """A small JPEG of an image, or None -- in which case serve the original.

    Uses `sips`, which ships with macOS, rather than adding Pillow: the hub's
    dependency list is four packages and a file browser is not a good reason to
    make it five. The cache key includes mtime and size, so an edited file
    re-renders without anything having to invalidate anything.
    """
    if classify(path) != "image":
        return None
    try:
        st = path.stat()
    except OSError:
        return None
    key = hashlib.sha1(
        f"{os.path.realpath(path)}|{st.st_mtime_ns}|{st.st_size}|{max_px}".encode()
    ).hexdigest()
    cached = cache_dir / f"{key}.jpg"
    if cached.is_file():
        return cached
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            (
                "sips", "-Z", str(max_px),
                "--setProperty", "format", "jpeg",
                "--out", str(cached),
                str(path),
            ),
            capture_output=True,
            timeout=THUMB_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0 or not cached.is_file():
        return None
    return cached
