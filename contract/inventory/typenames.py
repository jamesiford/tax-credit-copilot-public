"""A canonical, interpreter-independent spelling of a type annotation, built from the typing structure rather than `str()`.

`str(int | None)`, `str(typing.Optional[int])` and `str(typing.Union[A, B])` are spelled differently by Python 3.12 and 3.14 (a
union prints as `A | B` on one and `typing.Union[A, B]` on the other; `FastAPI` hands back either flavour for the same source).
The inventory must be a function of the product, not of the interpreter that read it (FINDING E-6).

Rules: a union is its members in declared order joined by ` | ` (`Optional[X]` is `X | None`); `Literal` keeps its values' `repr`;
a parameterised generic is `origin[args]`; `Annotated[X, ...]` is `X`; builtins are bare; any other class is `module.qualname`
(or just `qualname` with `short=True`, the style the response models were always written in). The harness replaces `datetime`
and `date` with frozen subclasses while the inventory runs, so those two are mapped back to the stdlib names.
"""
from __future__ import annotations

import types
import typing
from typing import Any

_UNION_ORIGINS = (typing.Union, getattr(types, "UnionType", typing.Union))
_ALIASES = {"contract.harness.freeze.FrozenDatetime": "datetime.datetime", "contract.harness.freeze.FrozenDate": "datetime.date"}


def _class(cls: type, short: bool) -> str:
    module, name = getattr(cls, "__module__", ""), getattr(cls, "__qualname__", None) or cls.__name__
    full = _ALIASES.get(f"{module}.{name}", f"{module}.{name}")
    if module == "builtins":
        return name
    return full.rsplit(".", 1)[-1] if short else full


def canonical(tp: Any, short: bool = False) -> str:
    if tp is None or tp is type(None):
        return "None"
    if tp is Any:
        return "Any"
    if tp is Ellipsis:
        return "..."
    origin, args = typing.get_origin(tp), typing.get_args(tp)
    if origin is typing.Annotated:
        return canonical(args[0], short)
    if origin in _UNION_ORIGINS:
        return " | ".join(canonical(a, short) for a in args)
    if origin is typing.Literal:
        return "Literal[" + ", ".join(repr(a) for a in args) + "]"
    if origin is not None:
        base = canonical(origin, short)
        return f"{base}[{', '.join(canonical(a, short) for a in args)}]" if args else base
    if isinstance(tp, type):
        return _class(tp, short)
    if isinstance(tp, typing.ForwardRef):
        return tp.__forward_arg__
    return str(tp)


def has_model(tp: Any) -> bool:
    """A pydantic model, alone or anywhere inside the generic/union arguments."""
    if hasattr(tp, "model_fields"):
        return True
    return any(has_model(a) for a in typing.get_args(tp))
