"""Seed an allowlisted offline feed; fresh locked restore verifies NuGet content hashes."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from stage import DEPLOY, ROOT


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    output = DEPLOY / ".staging" / "context" / "packages"
    if not output.is_dir():
        raise RuntimeError("Run stage.py before staging package archives.")
    located = subprocess.run(
        ["dotnet", "nuget", "locals", "global-packages", "--list"],
        cwd=ROOT / "dotnet", check=True, capture_output=True, text=True
    ).stdout.strip().split(": ", 1)[1]
    cache = Path(located)
    archives = {}
    for path in sorted((DEPLOY / "locks").glob("*/packages.lock.json")):
        lock = json.loads(path.read_text(encoding="utf-8"))
        for target in lock["dependencies"].values():
            for name, dependency in target.items():
                if "contentHash" in dependency:
                    archives[(name.lower(), dependency["resolved"])] = dependency["contentHash"]
    for (name, version), expected in archives.items():
        archive = cache / name / version / f"{name}.{version}.nupkg"
        if not archive.is_file() or archive.is_symlink():
            raise RuntimeError(f"Locked archive missing: {name} {version}.")
        actual = base64.b64encode(hashlib.sha512(archive.read_bytes()).digest()).decode("ascii")
        cached_hash = archive.with_suffix(".nupkg.sha512").read_text(encoding="utf-8").strip()
        metadata = json.loads((archive.parent / ".nupkg.metadata").read_text(encoding="utf-8"))
        # NuGet contentHash is signature-independent, unlike a raw archive SHA-512.
        if actual != cached_hash or metadata.get("contentHash") != expected:
            raise RuntimeError(f"Locked archive integrity mismatch: {name} {version}.")
        shutil.copyfile(archive, output / archive.name)
    print(f"Staged {len(archives)} allowlisted NuGet archives; fresh locked restore remains mandatory.")


if __name__ == "__main__":
    main()
