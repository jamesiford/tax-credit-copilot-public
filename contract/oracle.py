"""The interpreter the contract is recorded and verified on.

The product runs on Python 3.12, so 3.12 is the oracle. The recordings were first made on 3.14 and differed from 3.12 in the bytes of
zip/xlsx containers and one line of the inventory (FINDINGS E-1, E-6); pinning one interpreter makes `capture --check` mean
"the product's answer changed" and nothing else. The harness refuses to run on any other minor version unless the caller passes
`--allow-other-python`, which exists only for the cross-check and is stamped into every report.

Standard library only: this module is imported before the product is.
"""
from __future__ import annotations

import os
import subprocess
import sys

ORACLE_VERSION = (3, 12)
DEFAULT_PYTHON = r"C:\Projects\py312-oracle\.venv\Scripts\python.exe"
ALLOW_ENV = "CONTRACT_ALLOW_OTHER_PYTHON"
SETUP_HINT = "create it with: uv python install 3.12; uv venv C:\\Projects\\py312-oracle\\.venv --python 3.12; uv pip install --python C:\\Projects\\py312-oracle\\.venv\\Scripts\\python.exe -r backend\\requirements.txt (see contract/README.md)"


def python_path() -> str:
    """The interpreter child processes are started with: CONTRACT_PYTHON, else the 3.12 oracle environment."""
    return os.environ.get("CONTRACT_PYTHON") or DEFAULT_PYTHON


def allowed() -> bool:
    return os.environ.get(ALLOW_ENV) == "1"


def require(allow_other: bool = False) -> None:
    """Exit with a clear message unless this process is the oracle (or the cross-check was asked for explicitly)."""
    if allow_other:
        os.environ[ALLOW_ENV] = "1"
    if sys.version_info[:2] == ORACLE_VERSION or allowed():
        return
    sys.exit(
        f"contract: refusing to run on Python {sys.version.split()[0]} ({sys.executable}).\n"
        f"The oracle is Python {ORACLE_VERSION[0]}.{ORACLE_VERSION[1]}: point CONTRACT_PYTHON at a 3.12 interpreter "
        f"(default {DEFAULT_PYTHON}; {SETUP_HINT}).\n"
        "Pass --allow-other-python only for the cross-check; the output is stamped with the interpreter."
    )


def describe(python: str | None = None) -> dict:
    """Version and zlib build of an interpreter, for stamping into reports."""
    code = "import sys,zlib;print(sys.version.split()[0],zlib.ZLIB_VERSION,getattr(zlib,'ZLIBNG_VERSION',''))"
    try:
        out = subprocess.run([python or python_path(), "-c", code], capture_output=True, text=True, timeout=60).stdout.split()
    except OSError as exc:
        sys.exit(f"contract: cannot start {python or python_path()}: {exc}.\n{SETUP_HINT}")
    version, zlib_version = (out + ["?", "?"])[:2]
    return {"python": version, "zlib": zlib_version, "oracle": tuple(int(x) for x in version.split(".")[:2]) == ORACLE_VERSION if version != "?" else False,
            "allow_other_python": allowed()}
