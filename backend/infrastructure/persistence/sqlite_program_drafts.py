"""Program drafts over SQLite: local development and tests. [F05.2]

The same three tables as the Warehouse (migration 0005) and the same store code; only the transaction and the instant
encoding differ. Drafts have no runtime authority, so a local file here changes nothing a calculation reads.
"""
from __future__ import annotations

from pathlib import Path

from infrastructure.persistence.program_draft_store import ProgramDraftStore
from infrastructure.persistence.sqlite_run_batches import SqliteBackend

_SCHEMA = """
CREATE TABLE IF NOT EXISTS program_draft (
    draft_id TEXT PRIMARY KEY, proposed_code TEXT NOT NULL, name TEXT NOT NULL, jurisdiction_level TEXT NOT NULL, state TEXT,
    status TEXT NOT NULL, version INTEGER NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_by TEXT NOT NULL,
    updated_at TEXT NOT NULL, validation_json TEXT, review_requested_by TEXT, reviewer TEXT, decision TEXT, decision_comment TEXT,
    decided_at TEXT, approved_sha256 TEXT, exported_at TEXT, export_sha256 TEXT);
CREATE TABLE IF NOT EXISTS program_draft_document (
    draft_id TEXT NOT NULL, doc_key TEXT NOT NULL, content_json TEXT NOT NULL, content_sha256 TEXT NOT NULL,
    PRIMARY KEY (draft_id, doc_key));
CREATE TABLE IF NOT EXISTS program_draft_event (
    draft_id TEXT NOT NULL, seq INTEGER NOT NULL, event_type TEXT NOT NULL, actor TEXT NOT NULL, at TEXT NOT NULL,
    from_status TEXT, to_status TEXT, detail_json TEXT, PRIMARY KEY (draft_id, seq));
"""


class SqliteProgramDraftRepository(ProgramDraftStore):
    """The draft repository over a SQLite file or memory."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._backend = SqliteBackend(path, _SCHEMA)
        super().__init__(self._backend)

    def close(self) -> None:
        self._backend.close()
