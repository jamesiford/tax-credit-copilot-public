"""The six channel writes, each as a `_prepare` and a `_commit`. [CH-05, ADR-008]

Every one follows the same flow (`_prepare`, `_commit` below) so a write cannot
skip a step by being the odd one out:

  prepare  authorise -> build the real command (validates) -> preview the change
           from the command's own pure functions -> mint a token. Writes nothing.
  commit   build the command -> check the token (person, tool, arguments, expiry,
           single use) -> send it through the mediator, where the writer policy
           decides again -> record the outcome. A retry with the same idempotency
           key replays the first outcome and writes nothing.

Both steps run inside the channel auditor, so the trail shows `write_prepare`
then `write_commit`, and a refusal reads `refused`, not `error`.

The functions take the `principal` first. It is the one argument the schema does
not list, because it is who is asking, not part of the question.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from application.capabilities import _support as s
from application.capabilities.envelope import Provenance, ToolResult
from application.capabilities.write_specs import SPECS, WriteSpec
from application.channel_audit import AuditCall
from application.identity import Principal

_MONEY = "_usd"


def _clean(args: Mapping[str, Any]) -> dict[str, Any]:
    """Arguments without the unset ones, so prepare and commit hash the same thing."""
    return {k: v for k, v in args.items() if v is not None}


def _show(key: str, value: Any) -> str:
    if value is None:
        return s.ABSENT
    return s.cell(value, "money") if key.endswith(_MONEY) else str(value)


def _change_table(preview: Mapping[str, Any]) -> list[Any]:
    before, after = preview["before"] or {}, preview["after"]
    rows = [(k.replace("_", " "), _show(k, before.get(k)), _show(k, v)) for k, v in after.items()]
    return [s.table(("Field", "Now", "After"), rows)]


def _audit_call(spec: WriteSpec, kind: str, principal: Principal, args: Mapping[str, Any]) -> AuditCall:
    return AuditCall(
        tool_name=f"{spec.base}_{'prepare' if kind == 'write_prepare' else 'commit'}",
        action_kind=kind, actor=principal.as_acting_user(), args=args,
        client_id=args.get("client_id") if isinstance(args.get("client_id"), int) else None,
        tax_year=args.get("tax_year") if isinstance(args.get("tax_year"), int) else None,
    )


def _prepare(base: str, principal: Principal, args: Mapping[str, Any]) -> ToolResult:
    from application.wiring import get_channel_auditor, get_confirmation_service

    spec, args, service = SPECS[base], _clean(args), get_confirmation_service()
    with get_channel_auditor().audited(_audit_call(spec, "write_prepare", principal, args)) as handle:
        service.authorize(principal)
        preview = spec.preview(spec.build(principal, args))
        prepared = service.prepare(base, principal, args)
        handle.annotate(confirmation_ref=prepared.confirmation_id)
    facts = {
        "tool": base, "preview": preview,
        "confirmation": {"confirmation_id": prepared.confirmation_id, "token": prepared.token,
                         "expires_at": prepared.expires_at.isoformat()},
    }
    blocks = [
        s.heading(spec.summary), *_change_table(preview),
        s.callout("Nothing has changed yet. It is only written when you confirm."),
    ]
    return s.result(
        f"{base}_prepare", facts, blocks,
        provenance=Provenance(source="prepared change; nothing written"),
        warnings=["Prepared only: no change is made until the confirmation is committed."],
    )


def _commit(
    base: str, principal: Principal, arguments: Mapping[str, Any], token: str, idempotency_key: str,
) -> ToolResult:
    from application.wiring import get_channel_auditor, get_confirmation_service, get_mediator

    spec, args, service = SPECS[base], _clean(arguments), get_confirmation_service()
    with get_channel_auditor().audited(_audit_call(spec, "write_commit", principal, args)) as handle:
        command = spec.build(principal, args)
        committed = service.commit(
            base, principal, args, token, idempotency_key,
            lambda: get_mediator().send(command, principal=principal),
        )
        handle.annotate(confirmation_ref=committed.confirmation_id)
    note = ("Already done earlier; nothing was repeated." if committed.replayed
            else "Done. The change is recorded under your name.")
    return s.result(
        f"{base}_commit", {"tool": base, "replayed": committed.replayed, "result": committed.result},
        [s.heading(spec.summary), s.paragraph(note)],
        provenance=Provenance(source="mediator command; audited"),
    )


# -------------------------------------------------------------------- findings


def finding_resolve_prepare(
    principal: Principal, client_id: int, tax_year: int, finding_id: str, resolution: str,
    keep_worksite: str | None = None, note: str | None = None,
) -> ToolResult:
    return _prepare("finding_resolve", principal, dict(
        client_id=client_id, tax_year=tax_year, finding_id=finding_id, resolution=resolution,
        keep_worksite=keep_worksite, note=note))


def finding_resolve_commit(
    principal: Principal, confirmation_token: str, idempotency_key: str, arguments: Mapping[str, Any],
) -> ToolResult:
    return _commit("finding_resolve", principal, arguments, confirmation_token, idempotency_key)


def finding_reopen_prepare(principal: Principal, client_id: int, finding_id: str) -> ToolResult:
    return _prepare("finding_reopen", principal, dict(client_id=client_id, finding_id=finding_id))


def finding_reopen_commit(
    principal: Principal, confirmation_token: str, idempotency_key: str, arguments: Mapping[str, Any],
) -> ToolResult:
    return _commit("finding_reopen", principal, arguments, confirmation_token, idempotency_key)


# ----------------------------------------------------------------------- claims


def claim_transition_prepare(
    principal: Principal, client_id: int, program_code: str, tax_year: int, status: str,
    decline_reason: str | None = None,
) -> ToolResult:
    return _prepare("claim_transition", principal, dict(
        client_id=client_id, program_code=program_code, tax_year=tax_year, status=status,
        decline_reason=decline_reason))


def claim_transition_commit(
    principal: Principal, confirmation_token: str, idempotency_key: str, arguments: Mapping[str, Any],
) -> ToolResult:
    return _commit("claim_transition", principal, arguments, confirmation_token, idempotency_key)


def claim_record_prepare(
    principal: Principal, client_id: int, program_code: str, tax_year: int, status: str,
) -> ToolResult:
    return _prepare("claim_record", principal, dict(
        client_id=client_id, program_code=program_code, tax_year=tax_year, status=status))


def claim_record_commit(
    principal: Principal, confirmation_token: str, idempotency_key: str, arguments: Mapping[str, Any],
) -> ToolResult:
    return _commit("claim_record", principal, arguments, confirmation_token, idempotency_key)


# ------------------------------------------------- engagement and base year


def engagement_set_prepare(
    principal: Principal, client_id: int, program_code: str, scope: str, note: str | None = None,
) -> ToolResult:
    return _prepare("engagement_set", principal, dict(
        client_id=client_id, program_code=program_code, scope=scope, note=note))


def engagement_set_commit(
    principal: Principal, confirmation_token: str, idempotency_key: str, arguments: Mapping[str, Any],
) -> ToolResult:
    return _commit("engagement_set", principal, arguments, confirmation_token, idempotency_key)


def base_year_set_prepare(principal: Principal, client_id: int, unit_id: str, base_year: int) -> ToolResult:
    return _prepare("base_year_set", principal, dict(client_id=client_id, unit_id=unit_id, base_year=base_year))


def base_year_set_commit(
    principal: Principal, confirmation_token: str, idempotency_key: str, arguments: Mapping[str, Any],
) -> ToolResult:
    return _commit("base_year_set", principal, arguments, confirmation_token, idempotency_key)


# --------------------------------------------------------------- claim package


def claim_package_create_prepare(principal: Principal, client_id: int, tax_year: int) -> ToolResult:
    return _prepare("claim_package_create", principal, dict(client_id=client_id, tax_year=tax_year))


def claim_package_create_commit(
    principal: Principal, confirmation_token: str, idempotency_key: str, arguments: Mapping[str, Any],
) -> ToolResult:
    return _commit("claim_package_create", principal, arguments, confirmation_token, idempotency_key)
