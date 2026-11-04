"""The orchestrator: a Foundry hosted agent that answers in Teams and Copilot Chat. [CH-08]

It is a separate deployable from `backend/`. What it shares with the platform (the
catalog, the numeric guard, the composer, the model-access adapters) is COPIED by
`scripts/vendor-orchestrator.py` into `app/vendor/tcc_shared/`, which this file puts on
the import path when it exists. In the backend's own test run the real packages of the
same names are already importable and the vendored copy is not needed.
"""
from __future__ import annotations

import sys
from pathlib import Path

_VENDOR = Path(__file__).resolve().parent / "vendor" / "tcc_shared"
# Appended, not prepended: in the container nothing else provides these packages, and in the
# backend's test run the real packages of the same names must win.
if _VENDOR.is_dir() and str(_VENDOR) not in sys.path:
    sys.path.append(str(_VENDOR))
