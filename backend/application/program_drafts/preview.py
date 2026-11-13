"""Preview what a draft would calculate, on synthetic data, writing nothing. [F05.4, ADR-005]

The preview prices a draft's year packs with the engine's own functions: the Average Headcount from the draft's eligibility
floors (`tools/one_zero_pack` over the document in memory) and the benefit step (`tools/program_credit.credit_from_pack`). It
never writes: it touches no repository, no run, no claim and no file, builds the pack from the draft's documents without putting
them in the rules folder, and returns the result without storing it. Every figure is labelled **preview, not verified, not for
filing**, with the pack's unverified flags counted, because the numbers are only as good as statute nobody has checked yet.

The default data is the committed synthetic sample. A client's payroll is read only when the environment is itself synthetic or
`PROGRAM_PREVIEW_ALLOW_CUSTOMER_DATA` says so. [F05.4]
"""
from __future__ import annotations

from typing import Any

from application.assessment_inputs import MIN_MONTHS_TO_ASSESS, MIN_ROWS_TO_ASSESS, months_with_payroll, rows_for_state_year
from application.program_drafts.naming import pack_file_name
from application.program_drafts.validation import validate_draft
from config import get_settings, synthetic_environment
from domain.calculation.headcount import average_headcount
from domain.program_drafts import CustomerDataRefused, PreviewRefused, ProgramDraft

LABEL = "Preview, not verified, not for filing"
SAMPLE = "synthetic_sample"
CLIENT = "client"


def _flag_count(draft: ProgramDraft) -> int:
    from tools.pack_validation import _flags

    return sum(len(_flags(doc)) for doc in (draft.pack, *draft.years.values()) if doc)


def _rows(draft: ProgramDraft, dataset: str, client_id: int | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The payroll rows for the draft's state and a description of where they came from; refuses a customer source unless allowed."""
    state = draft.state or ""
    if dataset == SAMPLE:
        from tools.preview_sample import SAMPLE_DESCRIPTION, sample_rows

        return sample_rows(state), {"kind": SAMPLE, "description": SAMPLE_DESCRIPTION, "client_id": None}
    if dataset != CLIENT or client_id is None:
        raise PreviewRefused("dataset is synthetic_sample, or client with a client_id")
    if not (get_settings().programs.preview_allow_customer_data or synthetic_environment()):
        raise CustomerDataRefused(
            "a preview reads the committed synthetic sample only. Reading a client's payroll needs "
            "PROGRAM_PREVIEW_ALLOW_CUSTOMER_DATA=true (or an environment classified synthetic)")
    from application.source_ports import load_pay_periods

    _authorize_client(client_id)
    rows = [r for r in load_pay_periods(client_id) if (r.get("Work_State") or str(r.get("Worksite_ID", "")).partition("_")[0]).upper() == state]
    return rows, {"kind": CLIENT, "description": "A client's payroll in the draft's state, read for this preview only and never stored", "client_id": client_id}


def _authorize_client(client_id: int) -> None:
    """A client's payroll is read only for a client that exists and that the caller may act for.

    The existence check matters on a single-tenant source, which ignores the account id and would answer with the default
    tenant's payroll under whatever id was asked for.
    """
    from application import client_book
    from application.identity import ANONYMOUS, NotAuthorized, ambient_principal
    from application.services import get_client_authorizer

    if client_id not in {int(c["account_id"]) for c in client_book.clients_checked()}:
        raise PreviewRefused(f"client {client_id} is not in the client book")
    if not get_client_authorizer().is_authorized(ambient_principal() or ANONYMOUS, client_id):
        raise NotAuthorized(f"not authorized for client {client_id}")


def _year(rows: list[dict[str, Any]], state: str, year: int, doc: dict[str, Any]) -> tuple[float | None, dict[str, Any]]:
    """Average Headcount for one year under that year's own document, or `(None, why it was declined)`."""
    from tools.one_zero_pack import pack_from_document

    year_rows = rows_for_state_year(rows, state, year)
    if len(year_rows) < MIN_ROWS_TO_ASSESS:
        return None, {"tax_year": year, "reason": "no_payroll", "detail": f"the sample holds {len(year_rows)} row(s) for {state} in {year}"}
    months = months_with_payroll(year_rows)
    if months < MIN_MONTHS_TO_ASSESS:
        return None, {"tax_year": year, "reason": "payroll_too_thin", "detail": f"payroll covers {months} month(s) of {year}"}
    return average_headcount(rows, state, year, pack_from_document(doc, year)), {"rows_used": len(year_rows), "months_with_payroll": months}


def _price(draft: ProgramDraft, year: int, average: float, prior: float | None, facts: dict[str, Any]) -> dict[str, Any]:
    from tools.program_credit import credit_from_pack

    doc = draft.years[str(year)]
    base = average if prior is None else prior
    credit = credit_from_pack(doc, (draft.proposed_code, draft.state or "", pack_file_name(draft)), average, base)
    return {"tax_year": year, "average_headcount": round(average, 2), "prior_average_headcount": None if prior is None else round(prior, 2),
            "is_base_year": prior is None, "threshold_jobs": credit["threshold"], "qualifying_jobs": credit["qualifying_jobs"],
            "per_job_usd": credit["amount_per_job_usd"], "annual_credit_usd": credit["annual_credit_usd"],
            "benefit_period_years": credit["benefit_period_years"], "window": "calendar year (assumed for the sample)", **facts}


def _refuse_if_invalid(draft: ProgramDraft) -> None:
    result = validate_draft(draft)
    if result["valid"]:
        return
    first = "; ".join(f"{f['file']} {f['path']}: {f['message']}" for f in result["findings"] if f["severity"] == "error")[:400]
    raise PreviewRefused(f"validate and fix the draft first: {result['errors']} error(s). {first}")


def run(draft: ProgramDraft, *, dataset: str = SAMPLE, client_id: int | None = None, tax_years: tuple[int, ...] = ()) -> dict[str, Any]:
    """Price the draft's year packs over the chosen data and return the labelled result. Reads only; writes nothing."""
    if not draft.years:
        raise PreviewRefused("the draft has no year pack: add a tax year to preview a calculation")
    _refuse_if_invalid(draft)
    rows, source = _rows(draft, dataset, client_id)
    averages: dict[int, float] = {}
    facts: dict[int, dict[str, Any]] = {}
    declined: list[dict[str, Any]] = []
    for key, doc in sorted(draft.years.items()):
        average, info = _year(rows, draft.state or "", int(key), doc)
        if average is None:
            declined.append(info)
        else:
            averages[int(key)], facts[int(key)] = average, info
    wanted = set(tax_years) or set(averages)
    years = [_price(draft, y, averages[y], averages.get(y - 1), facts[y]) for y in sorted(averages) if y in wanted]
    return {"label": LABEL, "draft_id": draft.draft_id, "proposed_code": draft.proposed_code, "state": draft.state, "dataset": source,
            "unverified": True, "unverified_flags": _flag_count(draft), "years": years, "declined": declined,
            "persisted": False, "wrote_nothing": True}
