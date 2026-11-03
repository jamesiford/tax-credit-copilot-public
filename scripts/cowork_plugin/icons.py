"""The two PNG icons, drawn at build time. [CH-10]

The repository forbids committed raster images, and the package needs two: a
192x192 colour icon and a 32x32 outline icon (white on transparent). They are the
same mark as the SVGs under `channels/cowork/assets/` — a ring with a dot — drawn
here from first principles with the standard library only, so the build needs no
imaging dependency and the bytes are identical on every machine.
"""
from __future__ import annotations

import math
import struct
import zlib

WHITE = (255, 255, 255)
COLOR_SIZE, OUTLINE_SIZE = 192, 32


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    text = color.lstrip("#")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def _coverage(distance: float, inner: float, outer: float) -> float:
    """How much of a one-pixel cell at `distance` from the centre lies in the ring `inner..outer`."""
    return max(0.0, min(1.0, min(distance - inner, outer - distance) + 0.5))


def _mark(size: int, x: int, y: int) -> float:
    """Coverage of the mark (ring and dot) at one pixel, for a canvas of `size`."""
    centre, unit = (size - 1) / 2, size / 192
    distance = math.hypot(x - centre, y - centre)
    ring = _coverage(distance, 40 * unit, 60 * unit)
    dot = _coverage(distance, -1.0, 20 * unit)
    return max(ring, dot)


def _chunk(kind: bytes, data: bytes) -> bytes:
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def _png(width: int, height: int, color_type: int, rows: list[bytes]) -> bytes:
    raw = b"".join(b"\x00" + row for row in rows)
    header = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(raw, 9)) + _chunk(b"IEND", b"")


def color_icon(accent: str) -> bytes:
    """192x192, opaque: a white mark on the accent colour."""
    base, rows = _hex_to_rgb(accent), []
    for y in range(COLOR_SIZE):
        row = bytearray()
        for x in range(COLOR_SIZE):
            a = _mark(COLOR_SIZE, x, y)
            row += bytes(round(b + (w - b) * a) for b, w in zip(base, WHITE))
        rows.append(bytes(row))
    return _png(COLOR_SIZE, COLOR_SIZE, 2, rows)


def outline_icon() -> bytes:
    """32x32, white on a transparent background, as Teams asks of an outline icon."""
    rows = []
    for y in range(OUTLINE_SIZE):
        row = bytearray()
        for x in range(OUTLINE_SIZE):
            row += bytes((*WHITE, round(255 * _mark(OUTLINE_SIZE, x, y))))
        rows.append(bytes(row))
    return _png(OUTLINE_SIZE, OUTLINE_SIZE, 6, rows)


def png_size(data: bytes) -> tuple[int, int]:
    """Width and height of a PNG, read from its header; `ValueError` when it is not one."""
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError("not a PNG")
    return struct.unpack(">II", data[16:24])
