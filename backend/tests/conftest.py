"""Shared pytest fixtures for the backend test suite.

Conventions:
- `client` returns a FastAPI TestClient bound to the real app. Each test gets
  a fresh client (no shared mutable state across tests beyond the in-memory
  stores that intentionally persist within the process — settings, alerts,
  manual claims, scenario runs).
- `pay_period_rows` loads the 6,549-row BCS-shaped pay-period CSV once per
  session — it's read-only fixture data.
- `reset_settings_state` is autouse for tests that mutate `/api/settings` so
  one test's PUT doesn't leak into the next test's expectations.
"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

import pytest

# Ensure `backend/` is on sys.path so `import api.onezero` etc. work when
# pytest is invoked from the repo root.
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Also put `tests/` on the path so modules here can share helpers — notably
# `certified.py`, which holds the partner-reconciled figures asserted by both
# the direct parity gate and the source-schema round-trip. One definition, so
# the two cannot drift apart.
TESTS_ROOT = Path(__file__).resolve().parent
if str(TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(TESTS_ROOT))

# Pin the suite to the deterministic local CSV FIXTURE regardless of what
# `backend/.env` sets (a dev may have DATA_SOURCE=lakehouse for live work). This
# is the only place `csv` is selected: it is not a data source the product can
# choose, and it is not deployable. CI has no Fabric credential, so without
# this pin the certified figures could not be verified on a pull request.
# Set before `main` is imported so its load_dotenv(override=False) can't flip it.
os.environ["DATA_SOURCE"] = "csv"

# The opt-in live-Fabric tests (TCC_FABRIC_TESTS=1) still need somewhere to
# connect. Take only the connection settings from `.env`, never DATA_SOURCE —
# which is why this cannot just be `load_dotenv()`. The WAREHOUSE_ pair is the
# SQL endpoint behind tcc_gold; without it a live test errors in its fixture
# rather than skipping, which reads as a broken suite instead of an absent one.
for _name in (
    "FABRIC_WORKSPACE", "FABRIC_LAKEHOUSE", "FABRIC_EMPLOYEES_TABLE",
    "WAREHOUSE_SERVER", "WAREHOUSE_DATABASE",
):
    if not os.getenv(_name):
        _env = BACKEND_ROOT / ".env"
        if _env.exists():
            for _line in _env.read_text(encoding="utf-8").splitlines():
                if _line.startswith(f"{_name}="):
                    os.environ[_name] = _line.split("=", 1)[1].strip()
                    break

DATA_PAY_PERIODS = BACKEND_ROOT / "data" / "payroll_pay_periods.csv"


@pytest.fixture(scope="session")
def pay_period_rows() -> list[dict]:
    """Load the BCS-shaped pay-period CSV once for the whole test session."""
    if not DATA_PAY_PERIODS.exists():
        pytest.skip(
            f"{DATA_PAY_PERIODS} missing — run `python data/generate_pay_periods.py`."
        )
    with DATA_PAY_PERIODS.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture(autouse=True)
def restore_assumption_registries():
    """Undo any test-scoped assumption-set registration.

    `assumption_variants.runnable_set` registers a throwaway set in the engine's
    module-global registries so a superseded methodology can be exercised. Those
    registries are the definition of what the engine will run against real
    payroll, so a test must not be able to leave one behind.
    """
    from tools import reference_onezero, reference_source

    saved = (
        dict(reference_source._ASSUMPTION_PATHS),
        dict(reference_source._ASSUMPTION_COUNTS),
        dict(reference_onezero._ASSUMPTION_PATHS),
        dict(reference_onezero.STEP1_TO_ONEZERO),
    )
    yield
    for registry, snapshot in zip(
        (
            reference_source._ASSUMPTION_PATHS,
            reference_source._ASSUMPTION_COUNTS,
            reference_onezero._ASSUMPTION_PATHS,
            reference_onezero.STEP1_TO_ONEZERO,
        ),
        saved,
    ):
        registry.clear()
        registry.update(snapshot)


@pytest.fixture
def client():
    """FastAPI TestClient bound to the production app.

    Imported lazily so collection-time failures (e.g. missing optional deps)
    surface as test failures rather than collection errors.
    """
    from fastapi.testclient import TestClient

    from main import app

    return TestClient(app)


