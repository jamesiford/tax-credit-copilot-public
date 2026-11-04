"""Tiny valid PNGs for tests that need an icon of a given size without a renderer. [CH-15b]"""
from __future__ import annotations

import struct
import zlib


def _chunk(kind: bytes, data: bytes) -> bytes:
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def solid_png(size: int, *, alpha: bool, pixel: tuple[int, ...] | None = None) -> bytes:
    """A `size` x `size` 8-bit PNG, RGBA when `alpha` else RGB, every pixel the same."""
    pixel = pixel or ((255, 255, 255, 0) if alpha else (13, 40, 115))
    row = b"\x00" + bytes(pixel) * size
    header = struct.pack(">IIBBBBB", size, size, 8, 6 if alpha else 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(row * size)) + _chunk(b"IEND", b"")
