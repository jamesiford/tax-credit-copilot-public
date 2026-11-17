"""Only the current conductor check admits contact; its diagnostics remain memory-only."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
ORACLE = Path(r"C:\Projects\py312-oracle\.venv\Scripts\python.exe")


def guard_preflight() -> dict:
    command = ["dotnet", "run", "--no-build", "-c", "Release", "--project",
               str(HERE / "TaxCredit.Shadow.csproj"), "--", "--self-test"]
    try:
        result = subprocess.run(command, cwd=ROOT / "dotnet", capture_output=True, timeout=30, check=False)
        data = json.loads(result.stdout)
        passed = result.returncode == 0 and data == {"verdict": "passed", "inherited_fixtures": 31,
                                                   "templates": 3, "ownership_cases": 3}
        return {"verdict": "passed" if passed else "failed", "inherited_fixtures": 31 if passed else 0}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {"verdict": "failed", "inherited_fixtures": 0}


def oracle_preflight() -> bool:
    if sys.version_info[:2] != (3, 12):
        return False
    sys.path.insert(0, str(ROOT / "backend"))
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        import domain
    return Path(domain.__file__).resolve().is_relative_to(ROOT / "backend")


def capacity_admission(check: Path) -> dict:
    started = time.monotonic()
    approved = os.environ.get("TCC_SHADOW_APPROVED") == "yes"
    guard = guard_preflight()
    result = {"approved": approved, "guard": guard["verdict"], "capacity": "not-attempted",
              "oracle": "correct" if oracle_preflight() else "refused"}
    if not approved or guard["verdict"] != "passed" or result["oracle"] != "correct":
        return result
    environment = {**os.environ, "TCC_REPO": str(ROOT), "PYTHONPATH": str(ROOT / "backend"),
                   "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        probe = subprocess.run([str(ORACLE), str(check)], cwd=ROOT / "backend", env=environment,
                               capture_output=True, timeout=120, check=False)
        output = probe.stdout.decode("utf-8", "replace").strip()
        result["capacity"] = ("active" if probe.returncode == 0 and output == "ACTIVE"
                              else "paused" if output.startswith("PAUSED") else "unavailable")
        if result["capacity"] == "unavailable":
            result["reason"] = ("configuration-missing" if "WarehouseNotConfigured" in output
                                else "dependency-or-access-unproved")
    except subprocess.TimeoutExpired:
        result["capacity"] = "timeout"
    except OSError:
        result["capacity"] = "unavailable"
    result["combined_ms"] = round((time.monotonic() - started) * 1000, 3)
    return result
