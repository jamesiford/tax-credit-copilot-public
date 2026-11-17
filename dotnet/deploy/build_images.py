"""Build only bounded .NET Linux images; never push or contact a deployment target."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

from stage import DEPLOY, ROOT, SERVICES, context


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline-feed", action="store_true")
    parser.add_argument("--tag-prefix", default="tcc-w4")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,40}", args.tag_prefix):
        parser.error("Use a local simple image prefix.")
    source = context()
    if args.offline_feed:
        subprocess.run([sys.executable, str(DEPLOY / "stage_packages.py")], check=True)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    evidence = {"kind": "local-source-build", "commit": commit,
                "offline_feed": args.offline_feed, "images": {}}
    for service, name in SERVICES.items():
        image = f"{args.tag_prefix}-{service}:local"
        command = ["docker", "build", "--platform", "linux/amd64", "--progress", "plain",
                   "--build-arg", f"GIT_COMMIT={commit}",
                   "--file", str(source / "containers" / (name + ".Dockerfile")), "--tag", image]
        if args.offline_feed:
            command += ["--build-arg", "NUGET_SOURCE=/packages", "--build-arg", "NUGET_AUDIT=false"]
        subprocess.run(command + [str(source)], check=True)
        details = json.loads(subprocess.run(
            ["docker", "image", "inspect", image], check=True, capture_output=True, text=True
        ).stdout)[0]
        assert details["Architecture"] == "amd64" and details["Os"] == "linux"
        assert details["Config"]["User"] == "app"
        assert details["Config"]["Labels"]["org.opencontainers.image.revision"] == commit
        evidence["images"][service] = {
            "id": details["Id"], "architecture": details["Architecture"], "os": details["Os"],
            "user": details["Config"]["User"], "commit": commit, "revision_verified": True,
        }
    output = DEPLOY / ".artifacts" / "images.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("Four bounded nonroot linux/amd64 images built; no images pushed.")


if __name__ == "__main__":
    main()
