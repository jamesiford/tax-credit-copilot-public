"""`scripts/channel-smoke.ps1 -Since` hands channel-audit.py an ISO timestamp it can parse. [CH-14]

Found live: a local `$since` string in the script shadowed the `[datetime]$Since` parameter (PowerShell names are
case-insensitive), so the ISO text was converted back to a culture-formatted date ("11/3/2026 1:05:00 PM") and
channel-audit.py refused it. The script runs here for real against a stub channel-audit.py that parses its
`--since` exactly as the real one does (`datetime.fromisoformat`) and reports what it received.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PWSH = shutil.which("pwsh")

pytestmark = pytest.mark.skipif(PWSH is None, reason="PowerShell 7 (pwsh) is not installed")

STUB = '''
import argparse, sys
from datetime import datetime
p = argparse.ArgumentParser(); p.add_argument("--user"); p.add_argument("--since"); p.add_argument("--detail", action="store_true")
a = p.parse_args()
try:
    when = datetime.fromisoformat(a.since)
except ValueError as exc:
    print(f"bad date: {exc}", file=sys.stderr); sys.exit(2)
print(f"SINCE={a.since} PARSED={when.isoformat()} USER={a.user}")
'''


@pytest.fixture
def repo(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy(REPO / "scripts" / "channel-smoke.ps1", scripts / "channel-smoke.ps1")
    (scripts / "channel-audit.py").write_text(STUB, encoding="utf-8")
    return tmp_path


def smoke(repo, since_expression):
    program = f"& '{repo / 'scripts' / 'channel-smoke.ps1'}' -Since {since_expression} -UserOid 00000000-0000-0000-0000-000000000001"
    env = {**os.environ, "WAREHOUSE_SERVER": "x.example", "WAREHOUSE_DATABASE": "db", "PYTHONHOME": ""}
    env.pop("PYTHONHOME")
    return subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-Command", program], capture_output=True, text=True, env=env, timeout=120)


@pytest.mark.parametrize("expression,expected", [
    ("'2026-11-03T16:00:00Z'", "2026-11-03T16:00:00Z"),
    ("([datetime]'2026-11-03 13:05:00')", None),
    ("([datetime]::UtcNow.AddMinutes(-10))", None),
])
def test_the_audit_script_receives_an_iso_timestamp_it_can_parse(repo, expression, expected):
    done = smoke(repo, expression)
    assert done.returncode == 0, done.stdout + done.stderr
    line = next(l for l in done.stdout.splitlines() if l.startswith("SINCE="))
    since = line.split()[0].removeprefix("SINCE=")
    assert since.endswith("Z") and "T" in since and "/" not in since and "PM" not in since and "AM" not in since
    if expected:
        assert since == expected


def test_a_local_time_is_converted_to_utc_not_passed_through(repo):
    done = smoke(repo, "([datetime]::new(2026, 11, 3, 13, 5, 0, [DateTimeKind]::Utc))")
    assert "SINCE=2026-11-03T13:05:00Z" in done.stdout
