"""Print pinned versus latest for the AI SDKs. [AI-01]

    python scripts/check-sdk-versions.py            # offline-safe: pins only if there is no network
    python scripts/check-sdk-versions.py --strict   # exit 1 when a pinned package is behind

Latest comes from `pip index versions`, so it needs the network; without it the
script still prints the pins and says latest is unknown rather than failing. A
newer release is information, not an error: agent-framework-foundry bounds
azure-ai-projects, so the newest of each is not always installable together.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

PACKAGES = (
    "agent-framework-foundry", "azure-ai-projects", "azure-identity",
    "azure-monitor-opentelemetry", "httpx",
)
REQUIREMENTS = Path(__file__).resolve().parents[1] / "backend" / "requirements.txt"


def pinned(text: str) -> dict[str, str]:
    """`name==version` pins from a requirements file."""
    found = {}
    for line in text.splitlines():
        match = re.match(r"^([A-Za-z0-9_.\-]+)(?:\[[^\]]*\])?==([^\s#]+)", line.strip())
        if match:
            found[match.group(1).lower()] = match.group(2)
    return found


def latest(package: str) -> str | None:
    """The newest release pip can see, or None offline."""
    try:
        out = subprocess.run(
            [sys.executable, "-m", "pip", "index", "versions", package],
            capture_output=True, text=True, timeout=60, check=False,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r"^\S+ \(([^)]+)\)", out, re.MULTILINE)
    return match.group(1) if match else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    pins = pinned(REQUIREMENTS.read_text(encoding="utf-8"))
    behind = 0
    for package in PACKAGES:
        have, newest = pins.get(package, "(not pinned)"), latest(package)
        state = "latest unknown (offline?)" if newest is None else ("current" if newest == have else f"latest {newest}")
        behind += newest is not None and newest != have
        print(f"{package:<32} pinned {have:<12} {state}")
    return 1 if args.strict and behind else 0


if __name__ == "__main__":
    sys.exit(main())
