"""Record and verify the recordings.

    .\\contract\\py.ps1 -m contract.capture record [--scenario NAME ...] [--jobs 4]
    .\\contract\\py.ps1 -m contract.capture --check [--scenario NAME ...]     # fail if the Python code now answers differently

Each scenario runs in its own fresh process (`contract.harness.run_scenario`), so no state leaks between scenarios and a scenario
can be replayed alone.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SCENARIOS = ROOT / "contract" / "scenarios"
RECORDINGS = ROOT / "contract" / "recordings"
PYTHON = os.environ.get("CONTRACT_PYTHON", r"C:\Projects\GitHub\tax-credit-copilot-public\.venv\Scripts\python.exe")


def scenario_files(names: list[str] | None) -> list[Path]:
    files = sorted(SCENARIOS.glob("*.json"))
    return [f for f in files if not names or f.stem in names]


def run_one(scenario: Path, out: Path, base_url: str | None = None) -> tuple[str, float, str]:
    started = time.time()
    cmd = [PYTHON, "-m", "contract.harness.run_scenario", "--scenario", str(scenario), "--out", str(out)]
    if base_url:
        cmd += ["--base-url", base_url]
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.run(cmd, cwd=ROOT / "backend", env=env, capture_output=True, text=True, timeout=1800)
    tail = "\n".join((proc.stderr or "").splitlines()[-15:]) if proc.returncode else ""
    return scenario.stem, time.time() - started, tail


def normalised_text(path: Path) -> str:
    from contract import exchange, normalise

    records = exchange.load_records(path.read_text(encoding="utf-8"))
    return "".join(exchange.dump_record(r) + "\n" for r in normalise.apply_all(records))


def record(files: list[Path], jobs: int, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    failures = 0
    with cf.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(run_one, f, out_dir / f"{f.stem}.raw.jsonl") for f in files]
        for fut in cf.as_completed(futures):
            name, seconds, tail = fut.result()
            if tail:
                failures += 1
                print(f"FAILED {name} ({seconds:.0f}s)\n{tail}")
            else:
                (out_dir / f"{name}.jsonl").write_text(normalised_text(out_dir / f"{name}.raw.jsonl"), encoding="utf-8", newline="\n")
                (out_dir / f"{name}.raw.jsonl").unlink()
                print(f"recorded {name} ({seconds:.0f}s)")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs="?", choices=["record"], default=None)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--scenario", action="append")
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    files = scenario_files(args.scenario)
    if args.check:
        with tempfile.TemporaryDirectory(prefix="tcc-contract-check-") as tmp:
            failures = record(files, args.jobs, Path(tmp))
            changed = []
            for f in files:
                new, old = Path(tmp) / f"{f.stem}.jsonl", RECORDINGS / f"{f.stem}.jsonl"
                if not new.exists() or not old.exists() or hashlib.sha256(new.read_bytes()).digest() != hashlib.sha256(old.read_bytes()).digest():
                    changed.append(f.stem)
            if failures or changed:
                print("recordings differ from what the Python code now produces: " + ", ".join(changed or ["(a scenario failed to run)"]))
                return 1
            print(f"--check: {len(files)} recordings identical")
            return 0
    if args.command == "record":
        return 1 if record(files, args.jobs, RECORDINGS) else 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
