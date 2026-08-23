"""Images that live IN a channel, not beside it.

★ His direction, and it is the right one: *"you should be able to dump images into
these channel feeds, that is the direction you should go, don't point me elsewhere."*

Before this, the only way to show him a picture was to drop it in a shared folder and
tell him where to look — which is not showing someone a picture, it is filing one. An
image posted here becomes an ordinary `image` EVENT in the thread, so it arrives on
every client, in order, in the conversation it belongs to.

⚠️ CONTENT-ADDRESSED. The id is the sha256 of the bytes, so posting the same screenshot
twice costs one copy and the id is stable, cacheable and never guessable from a
filename. It also means a client can cache aggressively: an id can only ever refer to
one sequence of bytes.

⚠️ The type is sniffed from MAGIC BYTES, never from the filename. `Content-Type` and the
extension are both attacker-supplied on an upload path, and a client that trusts either
will happily render whatever it was told this was.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path

#: Generous: a phone screenshot is ~1-3 MB and a CAD render can be more. The cap exists
#: so a mistake cannot fill the disk, not to police what he sends.
MAX_IMAGE_BYTES = 32 * 1024 * 1024

#: Only formats every client can already draw without a decoder dependency.
SNIFFERS: tuple[tuple[bytes, str, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"GIF87a", "image/gif", "gif"),
    (b"GIF89a", "image/gif", "gif"),
)


class ImageError(Exception):
    """Rejected: too big, empty, or not an image we will serve."""


@dataclass(frozen=True)
class StoredImage:
    id: str
    media_type: str
    ext: str
    size: int
    width: int | None
    height: int | None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "media_type": self.media_type,
            "bytes": self.size,
            "width": self.width,
            "height": self.height,
        }


def sniff(data: bytes) -> tuple[str, str]:
    """(media_type, extension) from the magic bytes, or raise."""
    for magic, media_type, ext in SNIFFERS:
        if data.startswith(magic):
            return media_type, ext
    # WebP is RIFF....WEBP — a prefix check alone would match any RIFF file.
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    raise ImageError("not a PNG, JPEG, GIF or WebP")


def dimensions(data: bytes, media_type: str) -> tuple[int | None, int | None]:
    """Width/height without a decoder.

    ★ Worth the parsing: a client that knows the aspect ratio before the bytes arrive
    can reserve the right space, so a thread does not jump around as images load.
    Best-effort — an unreadable header is not a reason to refuse the image.
    """
    try:
        if media_type == "image/png" and len(data) >= 24:
            w, h = struct.unpack(">II", data[16:24])
            return int(w), int(h)
        if media_type == "image/gif" and len(data) >= 10:
            w, h = struct.unpack("<HH", data[6:10])
            return int(w), int(h)
        if media_type == "image/jpeg":
            i = 2
            while i + 9 < len(data):
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                # SOF0..SOF15, excluding the non-frame markers in that range
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                              0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    h, w = struct.unpack(">HH", data[i + 5:i + 9])
                    return int(w), int(h)
                seg = struct.unpack(">H", data[i + 2:i + 4])[0]
                i += 2 + seg
    except (struct.error, IndexError, ValueError):
        pass
    return None, None


def store(data: bytes, root: Path) -> StoredImage:
    """Put bytes in the store and describe them. Idempotent for identical bytes."""
    if not data:
        raise ImageError("refusing to store an empty image")
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageError(f"image is too large ({len(data)} bytes)")
    media_type, ext = sniff(data)
    digest = hashlib.sha256(data).hexdigest()
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{digest}.{ext}"
    if not target.exists():
        # ⚠️ Same .part-then-rename contract as the dropzone inbox: a reader must never
        # catch a half-written file, and here the reader is every connected client.
        part = target.with_name(target.name + ".part")
        try:
            part.write_bytes(data)
            part.replace(target)
        except OSError:
            part.unlink(missing_ok=True)
            raise
    w, h = dimensions(data, media_type)
    return StoredImage(digest, media_type, ext, len(data), w, h)


def path_for(image_id: str, root: Path) -> Path:
    """Locate stored bytes by id.

    ⚠️ The id is validated as hex, not merely joined. It arrives from a URL, and
    `root / "../../etc/passwd"` is a path traversal that a naive join would serve.
    """
    if not image_id or len(image_id) != 64 or not all(
        c in "0123456789abcdef" for c in image_id
    ):
        raise ImageError("not an image id")
    for _, _, ext in SNIFFERS + ((b"", "image/webp", "webp"),):
        candidate = root / f"{image_id}.{ext}"
        if candidate.exists():
            return candidate
    raise ImageError("no such image")
