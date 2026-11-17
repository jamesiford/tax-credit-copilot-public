"""JSON that keeps what a Python `json.loads` throws away: the original text of every number, and key order.

`loads` returns plain `dict` (insertion order = document order), `list`, `str`, `bool`, `None` and `Num` for every number, where
`Num.text` is exactly what the server wrote (`1.0`, `1`, `1e-05`, `39060`). `dumps` writes a tree back as compact JSON with the
number text verbatim and non-ASCII characters literal, so a recording line is itself valid JSON that preserves all of it.
"""
from __future__ import annotations

import json
import math
from decimal import Decimal
from typing import Any


class Num:
    """A JSON number as written."""

    __slots__ = ("text",)

    def __init__(self, text: str) -> None:
        self.text = text

    def __repr__(self) -> str:
        return f"Num({self.text})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Num) and other.text == self.text

    def __hash__(self) -> int:
        return hash(self.text)

    @property
    def value(self) -> Decimal | float:
        try:
            return Decimal(self.text)
        except Exception:  # NaN / Infinity spelled by Python's json
            return float(self.text)

    def is_integral_text(self) -> bool:
        return all(c in "-0123456789" for c in self.text)


class DuplicateKey(ValueError):
    pass


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DuplicateKey(key)
        out[key] = value
    return out


def loads(text: str | bytes) -> Any:
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    return json.loads(text, parse_float=Num, parse_int=Num, parse_constant=Num, object_pairs_hook=_pairs)


def _str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def dumps(tree: Any) -> str:
    out: list[str] = []
    _emit(tree, out)
    return "".join(out)


def _emit(node: Any, out: list[str]) -> None:
    if isinstance(node, dict):
        out.append("{")
        first = True
        for key, value in node.items():
            if not first:
                out.append(",")
            first = False
            out.append(_str(str(key)))
            out.append(":")
            _emit(value, out)
        out.append("}")
    elif isinstance(node, (list, tuple)):
        out.append("[")
        for i, value in enumerate(node):
            if i:
                out.append(",")
            _emit(value, out)
        out.append("]")
    elif isinstance(node, Num):
        out.append(node.text)
    elif isinstance(node, bool):
        out.append("true" if node else "false")
    elif node is None:
        out.append("null")
    elif isinstance(node, str):
        out.append(_str(node))
    elif isinstance(node, int):
        out.append(str(node))
    elif isinstance(node, float):
        out.append(repr(node) if math.isfinite(node) else "null")
    else:
        raise TypeError(f"cannot serialise {type(node).__name__}")


def to_plain(node: Any) -> Any:
    """A tree with `Num` replaced by int/float, for scenario variable capture and templating."""
    if isinstance(node, dict):
        return {k: to_plain(v) for k, v in node.items()}
    if isinstance(node, list):
        return [to_plain(v) for v in node]
    if isinstance(node, Num):
        return int(node.text) if node.is_integral_text() else float(node.text)
    return node
