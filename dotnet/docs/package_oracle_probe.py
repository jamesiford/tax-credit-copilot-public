"""Export public synthetic workbook evidence using the approved interpreter."""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]


async def main():
    from contract import oracle
    oracle.require(False)
    from contract.harness.world import build

    world = build("P1", ROOT / "dotnet" / "docs" / "package-probe-work")
    async with world.client() as client:
        response = await client.post("/api/clients/1001/packages?tax_year=2025")
        response.raise_for_status()
        package = response.json()
        download = await client.get(
            f"/api/clients/1001/artifacts/{package['artifact_id']}"
        )
        download.raise_for_status()
    destination = ROOT / "dotnet" / "docs" / "package-probe"
    destination.mkdir(exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        for member in archive.infolist():
            path = destination / member.filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.read(member))
        print(json.dumps([
            {"name": m.filename, "size": m.file_size,
             "sha256": hashlib.sha256(archive.read(m)).hexdigest()}
            for m in archive.infolist()
        ], indent=2))


if __name__ == "__main__":
    asyncio.run(main())
