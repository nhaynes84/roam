"""Images posted into a channel.

The interesting cases are all about trusting the wrong thing: a filename, a declared
Content-Type, or an id that came out of a URL.
"""

from __future__ import annotations

import struct

import pytest

import images

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + struct.pack(">II", 640, 480) + b"rest"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00\x10JFIF\x00" + b"\x00" * 20
GIF = b"GIF89a" + struct.pack("<HH", 320, 200) + b"\x00" * 8


class TestSniffing:
    def test_type_comes_from_magic_bytes(self):
        assert images.sniff(PNG) == ("image/png", "png")
        assert images.sniff(JPEG) == ("image/jpeg", "jpg")
        assert images.sniff(GIF) == ("image/gif", "gif")

    def test_a_riff_file_that_is_not_webp_is_refused(self):
        """RIFF is a container — a prefix check alone matches WAV and AVI too."""
        wav = b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE" + b"\x00" * 20
        with pytest.raises(images.ImageError):
            images.sniff(wav)
        webp = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 20
        assert images.sniff(webp) == ("image/webp", "webp")

    def test_something_that_is_not_an_image_is_refused(self):
        with pytest.raises(images.ImageError):
            images.sniff(b"#!/bin/sh\nrm -rf /\n")

    def test_a_png_name_does_not_make_it_a_png(self, tmp_path):
        """The filename and Content-Type are both attacker-supplied on upload."""
        with pytest.raises(images.ImageError):
            images.store(b"<html>not an image</html>", tmp_path)


class TestDimensions:
    def test_png_and_gif_headers(self):
        assert images.dimensions(PNG, "image/png") == (640, 480)
        assert images.dimensions(GIF, "image/gif") == (320, 200)

    def test_an_unreadable_header_is_not_fatal(self):
        """Best effort: no dimensions is a layout hint lost, not an image refused."""
        assert images.dimensions(b"\xff\xd8\xff", "image/jpeg") == (None, None)


class TestStore:
    def test_identical_bytes_store_once_and_share_an_id(self, tmp_path):
        a = images.store(PNG, tmp_path)
        b = images.store(PNG, tmp_path)
        assert a.id == b.id
        assert len(list(tmp_path.glob("*.png"))) == 1

    def test_different_bytes_get_different_ids(self, tmp_path):
        assert images.store(PNG, tmp_path).id != images.store(GIF, tmp_path).id

    def test_it_describes_what_it_stored(self, tmp_path):
        stored = images.store(PNG, tmp_path)
        assert stored.media_type == "image/png"
        assert (stored.width, stored.height) == (640, 480)
        assert stored.size == len(PNG)

    def test_empty_and_oversized_are_refused(self, tmp_path):
        with pytest.raises(images.ImageError):
            images.store(b"", tmp_path)
        big = PNG + b"\x00" * images.MAX_IMAGE_BYTES
        with pytest.raises(images.ImageError):
            images.store(big, tmp_path)

    def test_no_part_file_survives(self, tmp_path):
        """Every connected client is a reader; none may catch a half-written file."""
        images.store(PNG, tmp_path)
        assert list(tmp_path.glob("*.part")) == []


class TestLookup:
    def test_round_trips(self, tmp_path):
        stored = images.store(PNG, tmp_path)
        assert images.path_for(stored.id, tmp_path).read_bytes() == PNG

    @pytest.mark.parametrize("bad", [
        "../../../etc/passwd",
        "..%2f..%2fetc%2fpasswd",
        "",
        "nothex" * 10,
        "abc",
        "/etc/passwd",
    ])
    def test_an_id_from_a_url_cannot_escape_the_store(self, tmp_path, bad):
        with pytest.raises(images.ImageError):
            images.path_for(bad, tmp_path)

    def test_an_unknown_but_well_formed_id_is_a_miss_not_a_crash(self, tmp_path):
        with pytest.raises(images.ImageError):
            images.path_for("a" * 64, tmp_path)
