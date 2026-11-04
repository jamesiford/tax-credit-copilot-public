"""Tables that exist but are deliberately NOT queryable, each with its reason. [CH-16a]

The drift test fails when a table appears in the Warehouse DDL (or the lakehouse source
schema) that is neither modelled nor listed here. That is the point of this file: adding a
table forces a decision, and a decision with no reason is not accepted. To make one of
these queryable, model it in a `model_*.py` and delete the line here; the test refuses a
table that is on both lists.
"""
from __future__ import annotations

_OPERATIONAL = "Operational record written by the platform to run itself; not payroll or credit data."
_PLATFORM = "Platform audit or security record. Never exposed to the agent; the audit trail has its own readers."

EXCLUDED_WAREHOUSE_TABLES: dict[str, str] = {
    "tcc_ops.source_snapshot": "Lineage of the payroll a run consumed; reproducibility metadata, not an analytic dataset.",
    "tcc_ops.source_file_manifest": "Per-file hashes and counts for a snapshot; carries no client key to scope by.",
    "tcc_ops.excluded_record": "Employee-level audit rows with source employee ids; a later dataset behind the user lane if a question needs it.",
    "tcc_ops.manual_override": "Human overrides, with the person who made each; the engine tools report an overridden figure and say so.",
    "tcc_ops.exception_report_item": "Ingestion quality-control exceptions that name employee rows.",
    "tcc_ops.assumption_set_version": "Global methodology registry with no client key; the run manifest names the set used.",
    "tcc_ops.rule_pack_version": "Global statute registry with no client key; the run manifest names the pack used.",
    "tcc_ops.rule_change_audit": _PLATFORM,
    "tcc_ops.agent_action_audit": _PLATFORM,
    "tcc_ops.program_claim": "Claims hold seeded, unverified assertions; client_situation and the book tools own that reading.",
    "tcc_ops.program_engagement": _OPERATIONAL,
    "tcc_ops.agent_finding_resolution": _OPERATIONAL,
    "tcc_ops.artifact": _OPERATIONAL,
    "tcc_ops.artifact_access": _PLATFORM,
    "tcc_ops.schema_migration": "Schema bookkeeping with no client key.",
    "tcc_ops.client_config": "Per-client configuration the platform reads; not a question about payroll.",
    "tcc_ops.channel_audit": _PLATFORM,
    "tcc_ops.channel_user": _PLATFORM,
    "tcc_ops.channel_confirmation": _PLATFORM,
}

EXCLUDED_SOURCE_TABLES: dict[str, str] = {
    "Account": "The client record itself, including its name; the client is selected by the platform, never queried.",
    "Entity": "Legal entities with tax ids; no question needs it yet. Add with a decision.",
    "Employment": "Names the employee but carries no account key, so it cannot be scoped to one client.",
    "Address": "Shared lookup with no client key; reachable only through a declared join from Location.",
    "StateCountyZip": "Shared geography lookup with no client key.",
    "PayFrequency": "Shared lookup with no client key, inferred rather than supplied.",
    "EntityFiscalYearRules": "Fiscal calendars with no client key; the engine resolves the fiscal window.",
}
