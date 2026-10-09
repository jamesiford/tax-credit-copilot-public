"""`ArtifactRepository` over SQLite: development and CI. [BLOB-6]

Mirrors `tcc_ops.artifact` / `tcc_ops.artifact_access`. Append-only: a new claim
package for a client-year stamps `superseded_at` on the previous live one in the
same transaction; access rows are only ever inserted.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any

from application.artifacts import Artifact, ArtifactAccess

_SCHEMA = """
CREATE TABLE IF NOT EXISTS artifact (
    artifact_id       TEXT PRIMARY KEY,
    kind              TEXT NOT NULL CHECK (kind IN ('rule_source', 'claim_package')),
    client_id         INTEGER,
    program_code      TEXT,
    tax_year          INTEGER,
    run_id            TEXT,
    rule_pack_version TEXT,
    container_name    TEXT NOT NULL,
    blob_path         TEXT NOT NULL,
    file_name         TEXT NOT NULL,
    content_type      TEXT NOT NULL,
    size_bytes        INTEGER NOT NULL,
    sha256            TEXT NOT NULL,
    created_by        TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    retain_until      TEXT,
    superseded_at     TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_artifact_live_path
    ON artifact (container_name, blob_path) WHERE superseded_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_artifact_client ON artifact (client_id, kind, tax_year, created_at);

CREATE TABLE IF NOT EXISTS artifact_access (
    access_id    TEXT PRIMARY KEY,
    artifact_id  TEXT NOT NULL REFERENCES artifact (artifact_id),
    client_id    INTEGER,
    user_upn     TEXT NOT NULL,
    user_oid     TEXT,
    accessed_at  TEXT NOT NULL,
    outcome      TEXT NOT NULL CHECK (outcome IN ('served', 'denied', 'missing'))
);
CREATE INDEX IF NOT EXISTS ix_artifact_access_client ON artifact_access (client_id, accessed_at);
"""

ARTIFACT_COLUMNS = (
    "artifact_id", "kind", "client_id", "program_code", "tax_year", "run_id",
    "rule_pack_version", "container_name", "blob_path", "file_name", "content_type",
    "size_bytes", "sha256", "created_by", "created_at", "retain_until", "superseded_at",
)
ACCESS_COLUMNS = ("access_id", "artifact_id", "client_id", "user_upn", "user_oid", "accessed_at", "outcome")

_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "operational.db"


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, (datetime, date)) else value


def artifact_from_row(row: dict[str, Any], *, parse=lambda v: v) -> Artifact:
    def instant(v: Any) -> datetime | None:
        if v is None:
            return None
        return datetime.fromisoformat(v) if isinstance(v, str) else parse(v)

    retain = row.get("retain_until")
    if isinstance(retain, str):
        retain = date.fromisoformat(retain[:10])
    elif isinstance(retain, datetime):
        retain = retain.date()
    return Artifact(
        artifact_id=str(row["artifact_id"]),
        kind=row["kind"],
        client_id=int(row["client_id"]) if row["client_id"] is not None else None,
        program_code=row["program_code"],
        tax_year=int(row["tax_year"]) if row["tax_year"] is not None else None,
        run_id=row["run_id"],
        rule_pack_version=row["rule_pack_version"],
        container_name=row["container_name"],
        blob_path=row["blob_path"],
        file_name=row["file_name"],
        content_type=row["content_type"],
        size_bytes=int(row["size_bytes"]),
        sha256=str(row["sha256"]).strip(),
        created_by=row["created_by"],
        created_at=instant(row["created_at"]),
        retain_until=retain,
        superseded_at=instant(row["superseded_at"]),
    )


class SqliteArtifactRepository:
    is_durable = False

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else Path(os.getenv("OPERATIONAL_DB", _DEFAULT_PATH))
        self._local = threading.local()
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self.path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    def record(self, artifact: Artifact) -> Artifact:
        conn = self._connect()
        with conn:
            if artifact.kind == "claim_package":
                conn.execute(
                    "UPDATE artifact SET superseded_at = ? WHERE client_id = ? AND kind = ? "
                    "AND tax_year IS ? AND superseded_at IS NULL",
                    (_iso(artifact.created_at), artifact.client_id, artifact.kind, artifact.tax_year),
                )
            conn.execute(
                f"INSERT INTO artifact ({', '.join(ARTIFACT_COLUMNS)}) "
                f"VALUES ({', '.join('?' for _ in ARTIFACT_COLUMNS)})",
                [_iso(getattr(artifact, c)) for c in ARTIFACT_COLUMNS],
            )
        return artifact

    def find(self, artifact_id: str) -> Artifact | None:
        row = self._connect().execute("SELECT * FROM artifact WHERE artifact_id = ?", (artifact_id,)).fetchone()
        return artifact_from_row(dict(row)) if row else None

    def live(self, client_id: int, *, kind: str | None = None, tax_year: int | None = None) -> list[Artifact]:
        sql = "SELECT * FROM artifact WHERE client_id = ? AND superseded_at IS NULL"
        params: list[Any] = [client_id]
        if kind is not None:
            sql += " AND kind = ?"
            params.append(kind)
        if tax_year is not None:
            sql += " AND tax_year = ?"
            params.append(tax_year)
        rows = self._connect().execute(sql + " ORDER BY created_at, artifact_id", params).fetchall()
        return [artifact_from_row(dict(r)) for r in rows]

    def record_access(self, access: ArtifactAccess) -> ArtifactAccess:
        conn = self._connect()
        with conn:
            conn.execute(
                f"INSERT INTO artifact_access ({', '.join(ACCESS_COLUMNS)}) "
                f"VALUES ({', '.join('?' for _ in ACCESS_COLUMNS)})",
                [_iso(getattr(access, c)) for c in ACCESS_COLUMNS],
            )
        return access

    def accesses(self, client_id: int) -> list[ArtifactAccess]:
        rows = self._connect().execute(
            "SELECT * FROM artifact_access WHERE client_id = ? ORDER BY accessed_at, access_id", (client_id,)
        ).fetchall()
        return [
            ArtifactAccess(
                access_id=r["access_id"], artifact_id=r["artifact_id"], client_id=r["client_id"],
                user_upn=r["user_upn"], user_oid=r["user_oid"], outcome=r["outcome"],
                accessed_at=datetime.fromisoformat(r["accessed_at"]),
            )
            for r in rows
        ]
