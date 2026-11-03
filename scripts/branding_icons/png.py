"""Reading PNG headers and pixels with the standard library only. [CH-15b]

The icon renderer's output is checked (size, alpha, corner transparency) by tests and by the
Cowork build. A decoder this small needs no imaging dependency, so the check runs wherever Python
does, even where no renderer is installed.
"""
from __future__ import annotations

import struct
import zlib

SIGNATURE = b"\x89PNG\r\n\x1a\n"
_CHANNELS = {2: 3, 6: 4}


def is_png(data: bytes) -> bool:
    """True when `data` starts with the PNG signature and an IHDR chunk."""
    return data[:8] == SIGNATURE and data[12:16] == b"IHDR"


def png_size(data: bytes) -> tuple[int, int]:
    """Width and height from the header; `ValueError` when the bytes are not a PNG."""
    if not is_png(data):
        raise ValueError("not a PNG")
    return struct.unpack(">II", data[16:24])


def color_type(data: bytes) -> int:
    """The IHDR colour type (2 = RGB, 6 = RGBA); `ValueError` when the bytes are not a PNG."""
    if not is_png(data):
        raise ValueError("not a PNG")
    return data[25]


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else b if pb <= pc else c


def _unfilter(kind: int, line: bytearray, prior: bytearray, step: int) -> None:
    for i in range(len(line)):
        left = line[i - step] if i >= step else 0
        up = prior[i]
        corner = prior[i - step] if i >= step else 0
        base = (0, left, up, (left + up) // 2, _paeth(left, up, corner))[kind]
        line[i] = (line[i] + base) & 0xFF


def _idat(data: bytes) -> bytes:
    out, offset = b"", 8
    while offset < len(data):
        length, kind = struct.unpack(">I4s", data[offset:offset + 8])
        if kind == b"IDAT":
            out += data[offset + 8:offset + 8 + length]
        offset += 12 + length
    return out


def decode_rgba(data: bytes) -> tuple[int, int, list[tuple[int, int, int, int]]]:
    """Width, height and row-major RGBA pixels of an 8-bit RGB or RGBA PNG; `ValueError` otherwise."""
    width, height = png_size(data)
    if data[24] != 8 or data[25] not in _CHANNELS or data[28]:
        raise ValueError("only 8-bit, non-interlaced RGB or RGBA PNGs are supported")
    step = _CHANNELS[data[25]]
    raw, stride = zlib.decompress(_idat(data)), width * step
    prior, pixels = bytearray(stride), []
    for y in range(height):
        start = y * (stride + 1)
        line = bytearray(raw[start + 1:start + 1 + stride])
        _unfilter(raw[start], line, prior, step)
        for x in range(width):
            r, g, b, *alpha = line[x * step:(x + 1) * step]
            pixels.append((r, g, b, alpha[0] if alpha else 255))
        prior = line
    return width, height, pixels
