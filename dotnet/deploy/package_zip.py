"""Create a deterministic code zip only after verifying the publication manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from stage import DEPLOY


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", required=True, choices=["api", "gateway", "worker"])
    args = parser.parse_args()
    directory = DEPLOY / ".artifacts" / "publish" / args.service
    manifest_path = directory / "artifact-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {item["path"]: item["sha256"] for item in manifest["files"]}
    actual = {path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file()}
    if actual != set(expected) | {"artifact-manifest.json"} or manifest["service"] != args.service:
        raise RuntimeError("Publication contains missing, unmanifested or wrong-service files.")
    destination = DEPLOY / ".artifacts" / (args.service + ".zip")
    temporary = destination.with_suffix(".zip.tmp")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(actual):
                path = directory / name
                if path.is_symlink() or any(part.startswith(".env") for part in path.parts):
                    raise RuntimeError("Links and environment files cannot be packaged.")
                content = path.read_bytes()
                if name in expected and hashlib.sha256(content).hexdigest() != expected[name]:
                    raise RuntimeError("Publication checksum mismatch.")
                entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = (0o755 if name.endswith(".sh") else 0o644) << 16
                archive.writestr(entry, content)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(".zip.sha256").write_text(f"{digest}  {destination.name}\n", encoding="ascii")
    print(f"{args.service}: verified deterministic code zip and SHA-256 ready.")


if __name__ == "__main__":
    main()
