"""The program draft store, written once over a small backend so the Warehouse and SQLite cannot drift. [F05.2]

Same backend contract as the run batch queue (`table`, `bind`, `parse`, `page`, `transact`); the SQL is portable T-SQL that
SQLite also accepts. Three tables (migration 0005): the draft row, one row per document, and an append-only event log.
Every write is one transaction that also appends its event, so the trail cannot miss a change and a conflict leaves nothing
behind. A save names the version it read: `UPDATE ... WHERE version = ?` and a rowcount of 0 is `DraftConflict`.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from domain.program_drafts import (
    MAX_DOCUMENT_CHARS, DraftConflict, DraftEvent, DraftStatus, ProgramDraft, canonical_json,
)
from infrastructure.persistence.run_batch_store import Backend, Tx

_COLUMNS = (
    "draft_id", "proposed_code", "name", "jurisdiction_level", "state", "status", "version", "created_by", "created_at",
    "updated_by", "updated_at", "validation_json", "review_requested_by", "reviewer", "decision", "decision_comment",
    "decided_at", "approved_sha256", "exported_at", "export_sha256",
)
_UPDATABLE = _COLUMNS[2:]  # everything but the id and the code, which never change
_EVENT_COLUMNS = ("draft_id", "seq", "event_type", "actor", "at", "from_status", "to_status", "detail_json")
_LIVE = (DraftStatus.WITHDRAWN.value, DraftStatus.EXPORTED.value)


class ProgramDraftStore:
    """`ProgramDraftRepository` over any `Backend`."""

    is_durable = True

    def __init__(self, backend: Backend) -> None:
        self._b = backend
        self._t = {n: backend.table(n) for n in ("program_draft", "program_draft_document", "program_draft_event")}

    # ------------------------------------------------------------------ writes

    def create(self, draft: ProgramDraft, event: DraftEvent) -> None:
        def work(tx: Tx) -> None:
            tx.execute(f"INSERT INTO {self._t['program_draft']} ({', '.join(_COLUMNS)}) VALUES ({', '.join('?' * len(_COLUMNS))})",
                       self._values(draft))
            self._write_documents(tx, draft)
            self._append(tx, event)

        self._b.transact(work)

    def save(self, draft: ProgramDraft, expected_version: int, event: DraftEvent) -> None:
        def work(tx: Tx) -> None:
            sets = ", ".join(f"{c} = ?" for c in _UPDATABLE)
            values = dict(zip(_COLUMNS, self._values(draft)))
            result = tx.execute(f"UPDATE {self._t['program_draft']} SET {sets} WHERE draft_id = ? AND version = ?",
                                [values[c] for c in _UPDATABLE] + [draft.draft_id, expected_version])
            if result.rowcount != 1:
                raise DraftConflict(f"draft {draft.draft_id} changed since it was read (expected version {expected_version}); reload it and retry")
            self._write_documents(tx, draft)
            self._append(tx, event)

        self._b.transact(work)

    def _values(self, d: ProgramDraft) -> list[Any]:
        bind = self._b.bind
        validation = canonical_json(d.validation) if d.validation is not None else None
        if validation is not None and len(validation) > MAX_DOCUMENT_CHARS:
            raise ValueError("the validation result is too large to store; it is capped before it reaches the store")
        return [d.draft_id, d.proposed_code, d.name, d.jurisdiction_level, d.state, d.status.value, d.version, d.created_by,
                bind(d.created_at), d.updated_by, bind(d.updated_at), validation, d.review_requested_by, d.reviewer, d.decision,
                d.decision_comment, bind(d.decided_at), d.approved_sha256, bind(d.exported_at), d.export_sha256]

    def _write_documents(self, tx: Tx, draft: ProgramDraft) -> None:
        table = self._t["program_draft_document"]
        tx.execute(f"DELETE FROM {table} WHERE draft_id = ?", [draft.draft_id])
        docs = ({"pack": draft.pack} if draft.pack is not None else {}) | dict(draft.years)
        for key, document in docs.items():
            text = canonical_json(document)
            if len(text) > MAX_DOCUMENT_CHARS:
                raise ValueError(f"document {key!r} is {len(text)} characters; the store holds at most {MAX_DOCUMENT_CHARS} per document")
            tx.execute(f"INSERT INTO {table} (draft_id, doc_key, content_json, content_sha256) VALUES (?, ?, ?, ?)",
                       [draft.draft_id, key, text, hashlib.sha256(text.encode('utf-8')).hexdigest()])

    def _append(self, tx: Tx, event: DraftEvent) -> None:
        table = self._t["program_draft_event"]
        last = tx.execute(f"SELECT MAX(seq) AS max_seq FROM {table} WHERE draft_id = ?", [event.draft_id]).rows
        seq = int(last[0]["max_seq"] or 0) + 1 if last else 1
        tx.execute(f"INSERT INTO {table} ({', '.join(_EVENT_COLUMNS)}) VALUES ({', '.join('?' * len(_EVENT_COLUMNS))})",
                   [event.draft_id, seq, event.event_type, event.actor, self._b.bind(event.at), event.from_status, event.to_status,
                    canonical_json(event.detail) if event.detail else None])

    # ------------------------------------------------------------------ reads

    def get(self, draft_id: str) -> ProgramDraft | None:
        def work(tx: Tx) -> ProgramDraft | None:
            found = tx.execute(f"SELECT {', '.join(_COLUMNS)} FROM {self._t['program_draft']} WHERE draft_id = ?", [draft_id]).rows
            return self._hydrate(tx, found[0]) if found else None

        return self._b.transact(work)

    def live_for_code(self, proposed_code: str) -> ProgramDraft | None:
        def work(tx: Tx) -> ProgramDraft | None:
            found = tx.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM {self._t['program_draft']} WHERE proposed_code = ? "
                f"AND status NOT IN ('{_LIVE[0]}', '{_LIVE[1]}') ORDER BY created_at", [proposed_code]).rows
            return self._hydrate(tx, found[0]) if found else None

        return self._b.transact(work)

    def list_drafts(self, status: str | None = None, limit: int = 50, offset: int = 0) -> tuple[list[ProgramDraft], int]:
        where, args = ("WHERE status = ?", [status]) if status else ("", [])
        clause, paging = self._b.page(limit, offset)

        def work(tx: Tx) -> tuple[list[ProgramDraft], int]:
            total = tx.execute(f"SELECT COUNT(*) AS n FROM {self._t['program_draft']} {where}", args).rows[0]["n"]
            found = tx.execute(f"SELECT {', '.join(_COLUMNS)} FROM {self._t['program_draft']} {where} "
                               f"ORDER BY updated_at DESC, draft_id {clause}", args + paging).rows
            return [self._hydrate(tx, r, documents=False) for r in found], int(total)

        return self._b.transact(work)

    def events(self, draft_id: str) -> list[DraftEvent]:
        found = self._b.transact(lambda tx: tx.execute(
            f"SELECT {', '.join(_EVENT_COLUMNS)} FROM {self._t['program_draft_event']} WHERE draft_id = ? ORDER BY seq", [draft_id]).rows)
        return [DraftEvent(draft_id=r["draft_id"], seq=int(r["seq"]), event_type=r["event_type"], actor=r["actor"],
                           at=self._b.parse(r["at"]), from_status=r["from_status"], to_status=r["to_status"],
                           detail=json.loads(r["detail_json"]) if r["detail_json"] else {}) for r in found]

    def _hydrate(self, tx: Tx, row: dict[str, Any], documents: bool = True) -> ProgramDraft:
        pack: dict[str, Any] | None = None
        years: dict[str, dict[str, Any]] = {}
        if documents:
            docs = tx.execute(f"SELECT doc_key, content_json FROM {self._t['program_draft_document']} WHERE draft_id = ? ORDER BY doc_key",
                              [row["draft_id"]]).rows
            for d in docs:
                if d["doc_key"] == "pack":
                    pack = json.loads(d["content_json"])
                else:
                    years[d["doc_key"]] = json.loads(d["content_json"])
        parse: Any = self._b.parse
        return ProgramDraft(
            draft_id=row["draft_id"], proposed_code=row["proposed_code"], name=row["name"], jurisdiction_level=row["jurisdiction_level"],
            state=row["state"], status=DraftStatus(row["status"]), version=int(row["version"]), created_by=row["created_by"],
            created_at=parse(row["created_at"]), updated_by=row["updated_by"], updated_at=parse(row["updated_at"]), pack=pack, years=years,
            validation=json.loads(row["validation_json"]) if row["validation_json"] else None,
            review_requested_by=row["review_requested_by"], reviewer=row["reviewer"], decision=row["decision"],
            decision_comment=row["decision_comment"], decided_at=parse(row["decided_at"]), approved_sha256=row["approved_sha256"],
            exported_at=parse(row["exported_at"]), export_sha256=row["export_sha256"],
        )
