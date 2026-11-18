"""The pinned oracle: CPython 3.12.

The product runs on Python 3.12 (App Service for the API, worker and gateway; CI), so 3.12 behaviour is the
specification the C# port reproduces. Later CPython releases differ in ways that change bits (``sum()`` of an int
after a float, the Unicode database), so every script that produces or serves oracle output calls ``require()``
first and refuses to run on anything else.

Create the oracle environment once:

    uv python install 3.12
    uv venv --python 3.12 C:\\Projects\\py312-oracle\\.venv
"""
from __future__ import annotations

import sys

REQUIRED = (3, 12)
FLAG = "--allow-other-python"

HOW_TO_CREATE = (
    "The parity oracle is CPython 3.12 (the interpreter the product runs on), but this is Python "
    "{found}. Create the oracle environment with:\n"
    "    uv python install 3.12\n"
    "    uv venv --python 3.12 C:\\Projects\\py312-oracle\\.venv\n"
    "then run this script with C:\\Projects\\py312-oracle\\.venv\\Scripts\\python.exe (set ORACLE_PYTHON to it for the .NET tests). "
    "For exploratory use only, pass " + FLAG + " (the output is stamped and the .NET tests reject it)."
)


def require(argv: list[str] | None = None) -> bool:
    """Exit unless running on CPython 3.12; returns True when the exploratory flag overrides the check.

    The flag is removed from ``argv`` (default ``sys.argv``) so argparse never sees it.
    """
    argv = sys.argv if argv is None else argv
    override = FLAG in argv
    if override:
        argv.remove(FLAG)
    if sys.version_info[:2] != REQUIRED and not override:
        sys.stderr.write(HOW_TO_CREATE.format(found=sys.version.split()[0]) + "\n")
        raise SystemExit(2)
    return override


def stamp() -> dict:
    """Meta fields identifying the interpreter, including the exploratory override."""
    meta: dict = {"python": sys.version.split()[0]}
    if sys.version_info[:2] != REQUIRED:
        meta["allow_other_python"] = True
    return meta
