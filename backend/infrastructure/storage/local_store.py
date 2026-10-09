"""Artifact bytes on the local filesystem. Development and CI only. [BLOB-6]

Not durable on App Service (the filesystem is not the system of record), so a
deployed process refuses `ARTIFACT_STORE=local` at startup.
"""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

_DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "data" / "artifacts"


class LocalArtifactStore:
    is_durable = False

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or os.getenv("ARTIFACT_LOCAL_ROOT") or _DEFAULT_ROOT)

    def _path(self, container: str, path: str) -> Path:
        relative = PurePosixPath(path)
        if relative.is_absolute() or ".." in relative.parts or not container.isidentifier():
            raise ValueError(f"refusing artifact path {container}/{path}")
        return self.root / container / Path(*relative.parts)

    def put(self, container: str, path: str, data: bytes, content_type: str) -> None:
        target = self._path(container, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError(f"{container}/{path} exists; blob paths are never reused")
        target.write_bytes(data)

    def get(self, container: str, path: str) -> bytes | None:
        target = self._path(container, path)
        return target.read_bytes() if target.is_file() else None
