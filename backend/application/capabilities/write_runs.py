"""The `run_batch` channel write: how it is built and previewed. [ADR-012, CH-05]

Split from `write_specs` by size. It follows the same contract as every other write there: `build` makes the SAME
mediator command the commit sends (authored by the person, never the gateway), and `preview` is the dry run, which writes
nothing and reads no payroll. `InvalidWrite` is imported where it is raised because `write_specs` imports this module.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from application.identity import Principal
from application.mediator import Command

RUN_KINDS = ("assess", "calculate", "assess_and_calculate")
RUN_SCOPES = ("one", "list", "filter", "all")
_FIRST_CLIENTS = 5


def _ints(a: Mapping[str, Any], name: str) -> tuple[int, ...]:
    from application.capabilities.write_specs import InvalidWrite

    value = a.get(name)
    if value is None:
        return ()
    if not isinstance(value, list) or any(isinstance(v, bool) or not isinstance(v, int) for v in value):
        raise InvalidWrite(f"{name} must be a list of integers")
    return tuple(value)


def _checked_scope(a: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    """The scope object and the kind, or `InvalidWrite` saying which is wrong."""
    from application.capabilities.write_specs import InvalidWrite

    scope, kind = a.get("scope"), a.get("kind", "calculate")
    ok = isinstance(scope, dict) and scope.get("kind") in RUN_SCOPES and kind in RUN_KINDS
    if not ok or not isinstance(scope.get("filter") or {}, dict):
        raise InvalidWrite(f"scope.kind must be one of {list(RUN_SCOPES)}, kind one of {list(RUN_KINDS)}, filter an object")
    return scope, kind


def build_run_batch(principal: Principal, a: Mapping[str, Any]) -> Command:
    """The same command the portal sends, authored by the person; building it validates the request."""
    from application.capabilities.write_specs import InvalidWrite
    from application.commands.enqueue_run_batch import EnqueueRunBatchCommand

    scope, kind = _checked_scope(a)
    options, confirm = a.get("options") or {}, a.get("confirm_items")
    command = EnqueueRunBatchCommand(
        actor=principal.actor, kind=kind, scope_kind=scope["kind"], client_ids=_ints(scope, "account_ids"),
        filter=dict(scope.get("filter") or {}), program_code=a.get("program_code"), tax_years=_ints(a, "tax_years"),
        force=bool(options.get("force", False)), skip_unchanged=bool(options.get("skip_unchanged", False)), refresh_once=bool(options.get("refresh_once", True)),
        confirm_items=confirm if isinstance(confirm, int) and not isinstance(confirm, bool) else None,
    )
    try:
        command.request()
    except ValueError as exc:
        raise InvalidWrite(str(exc)) from exc
    return command


def preview_run_batch(c: Any) -> dict[str, Any]:
    """The dry run: counts in scope, what is known about the last runs and unavailable clients, nothing written.

    Above the confirmation threshold the preview REFUSES until the count is in the arguments, so the person has been
    told the number before anything can be committed (the portal's typed confirmation, in two steps).
    """
    from application.capabilities.write_specs import InvalidWrite
    from application.queries.run_batch_reads import PreviewRunBatchQuery
    from application.runs.errors import RunBatchRefused
    from application.services import get_mediator

    try:
        p = get_mediator().send(PreviewRunBatchQuery(
            kind=c.kind, scope_kind=c.scope_kind, client_ids=c.client_ids, filter=c.filter, program_code=c.program_code,
            tax_years=c.tax_years, force=c.force, skip_unchanged=c.skip_unchanged, refresh_once=c.refresh_once))
    except RunBatchRefused as exc:
        raise InvalidWrite(str(exc)) from exc
    if p["over_size_limit"]:
        raise InvalidWrite(f"This selects {p['items']} runs, over the limit of {p['max_items']}. Narrow the selection.")
    if p["requires_confirmation"] and c.confirm_items != p["items"]:
        raise InvalidWrite(
            f"This would queue {p['items']} runs for {p['clients']} clients, above {p['confirm_above']}, so the person "
            f"must confirm the count. Tell them these numbers; if they agree, prepare again with confirm_items={p['items']}.")
    return {"before": None, "after": _after(c, p)}


def _after(c: Any, p: dict[str, Any]) -> dict[str, Any]:
    """The facts the person is shown before confirming."""
    return {
        "kind": c.kind.replace("_", " "), "clients": p["clients"], "runs to queue": p["items"],
        "tax years": ", ".join(str(y) for y in p["years"]) if isinstance(p["years"], list) else p["years"],
        "never calculated": p["never_run"], "may be skipped (an upper bound, decided as each run starts)": (
            p["skip_candidates_upper_bound"]),
        "unavailable clients": len(p["unavailable"]), "skip unchanged clients": "yes" if p["skip_unchanged"] and not p["force"] else "no (every item runs)",
        "programs": ", ".join(f"{k}: {v}" for k, v in sorted(p["programs"].items())),
        "first clients": ", ".join(str(i["client_name"] or i["client_id"]) for i in p["first_items"][:_FIRST_CLIENTS]),
    }
