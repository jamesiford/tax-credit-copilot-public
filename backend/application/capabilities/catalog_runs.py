"""The run batch capabilities' catalog entries: one write pair and two reads. [ADR-012]

Split from `catalog` by size. The write is `run_batch_prepare` / `run_batch_commit` (the usual two steps), the reads are
`run_batch_status` and `run_batch_list`. None names a client, so none needs one in the conversation; the clients a batch
covers travel as `scope.account_ids`, a filter or "all", and the model-facing schema never carries the reader's own
client (the orchestrator test pins that nothing in it reads `client_id`).
"""
from __future__ import annotations

from application.capabilities.catalog_types import (
    _CLIENT_ID, _PROGRAM, _TAX_YEAR, CapabilitySpec, _object, _read, _write_pair,
)

RUN_WRITES: tuple[CapabilitySpec, ...] = (
    *_write_pair(
        "run_batch",
        "Run assessments or calculations for one client, a list, a filtered group or all clients as a tracked batch. "
        "Always preview first: the preview gives the counts in scope and an upper bound on skips, never a promise. "
        "Above the confirmation threshold, tell the person the numbers and prepare again with confirm_items.",
        {"scope": _object(
            {"kind": {"type": "string", "enum": ["one", "list", "filter", "all"]},
             "account_ids": {"type": "array", "items": _CLIENT_ID, "maxItems": 200,
                             "description": "For kind one or list: the accounts to run."},
             "filter": _object(
                 {"band": {"type": "string"}, "state": {"type": "string"}, "program": {"type": "string"},
                  "year": {"type": "integer"}, "outcome": {"type": "string"}, "status": {"type": "string"},
                  "unassessed": {"type": "boolean"}, "unavailable": {"type": "boolean"}}, ()),
             }, ("kind",)),
         "kind": {"type": "string", "enum": ["assess", "calculate", "assess_and_calculate"], "default": "calculate"},
         "program_code": _PROGRAM,
         "tax_years": {"type": "array", "items": _TAX_YEAR, "maxItems": 12,
                       "description": "Empty: each client's latest runnable year."},
         "options": _object(
             {"force": {"type": "boolean", "description": "Run even if the last run already answers it."},
              "refresh_once": {"type": "boolean", "default": True}}, ()),
         "confirm_items": {"type": "integer", "description": "The run count the person confirmed, when the preview asks for it."}},
        ("scope",), needs_client=False,
    ),
)

RUN_READS: tuple[CapabilitySpec, ...] = (
    _read(
        "run_batch_status", "A run batch's progress: status, counts by outcome and any failures by cause. Names no client. Omit batch_id for the latest.",
        {"batch_id": {"type": "string", "maxLength": 64}}, needs_client=False,
    ),
    _read(
        "run_batch_list", "The most recent run batches, newest first, with status and progress. Names no client.",
        {"limit": {"type": "integer", "minimum": 1, "maximum": 25, "default": 5},
         "status": {"type": "string", "enum": ["queued", "running", "succeeded", "partial", "failed", "cancelled"]}},
        needs_client=False,
    ),
)
