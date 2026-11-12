"""Where a client's fiscal year actually comes from.

`EntityFiscalYearRules` has been in the source schema, populated for every
tenant and round-tripped through Delta since the schema was written — and
nothing read it. The engine took its fiscal year from a single global setting
instead, which is one accounting year for the whole application.

This is the adapter that reads the fact. When the fact is absent it says so
rather than inventing one; `assumed_calendar_window` carries the flag.
"""
from __future__ import annotations

import logging
from datetime import date

from domain.calculation.fiscal import (
    FiscalWindow,
    TaxYearLabel,
    assumed_calendar_window,
    window_from_client_rules,
)


log = logging.getLogger(__name__)


def _as_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _fiscal_rules(account_id: int) -> list | None:
    """The client's fiscal rules, by the cheapest route that can answer.

    SQL first. If it is configured and fails, the answer is "could not read" (None), which the caller
    turns into a flagged calendar-year assumption: it does NOT fall through to another store. The
    fallback to the lakehouse is opt-in (`SOURCE_FALLBACK=delta`) and, even then, is a bounded read of
    `Entity` and `EntityFiscalYearRules` rather than the ten-table load it used to be (~132s cold).

    None means "could not read"; an empty list means "read it, the client has no rule". Those are
    different facts: the second is a real gap in the source, the first is an outage, and an outage
    must not silently decide statute. Both are logged, and both end in `assumed_calendar`.
    """
    from infrastructure.persistence.source_sql import SourceSqlReader

    reader = SourceSqlReader()
    if reader.is_configured():
        rules, may_fall_back = _rules_over_sql(reader, account_id)
        if rules is not None or not may_fall_back:
            return rules
    return _rules_from_lakehouse(account_id)


def _rules_over_sql(reader, account_id: int) -> tuple[list | None, bool]:
    """(rules, may_fall_back). `rules` is None when SQL failed; `may_fall_back` only with SOURCE_FALLBACK=delta."""
    from application.errors import as_dependency_failure
    from config import get_settings

    try:
        return reader.fiscal_year_rules(int(account_id)), False
    except Exception as exc:  # noqa: BLE001 - classified below; a bug in our code is re-raised
        if as_dependency_failure("source_sql", exc) is None:
            raise
        fallback = get_settings().data_source.source_fallback == "delta"
        log.warning(
            "fiscal rules for account %s could not be read over SQL (%s); %s", account_id, type(exc).__name__,
            "SOURCE_FALLBACK=delta, so reading Entity and EntityFiscalYearRules from the lakehouse instead."
            if fallback else
            "the window is assumed to be a calendar year. Fix the SQL path, or set SOURCE_FALLBACK=delta to read "
            "them from the lakehouse.",
        )
        return None, fallback


def _rules_from_lakehouse(account_id: int) -> list | None:
    """A bounded lakehouse read of the two small tables; None when it cannot be done."""
    from application.errors import as_dependency_failure
    from data.source.from_fabric import FabricLakehouseReader

    delta = FabricLakehouseReader()
    if not delta.is_configured():
        return None
    try:
        return delta.fiscal_year_rules(int(account_id))
    except Exception as exc:  # noqa: BLE001 - an outage must not decide statute; a bug in our code is re-raised
        if as_dependency_failure("source_lakehouse", exc) is None:
            raise
        log.warning("fiscal rules for account %s could not be read from the lakehouse (%s); the window is assumed.",
                    account_id, type(exc).__name__)
        return None


def _rules_with_overrides(account_id: int) -> list | None:
    """The client's fiscal rules in provider order: source, then app-owned override; None when neither has one.

    Under the `strict` policy a client with no rule from any provider raises `FiscalRulesMissing` instead of
    quietly getting a calendar year. Under `assume` (the default) None becomes a window flagged `assumed`.
    """
    rules = _fiscal_rules(account_id)
    if rules:
        return rules
    from data.lookups import fiscal_override_rules, fiscal_rules_policy

    overridden = fiscal_override_rules(account_id)
    if overridden:
        return overridden
    if fiscal_rules_policy() == "strict":
        from application.errors import FiscalRulesMissing

        raise FiscalRulesMissing(account_id)
    return rules


def client_fiscal_window(
    account_id: int | None,
    tax_year: int,
    convention: TaxYearLabel,
) -> FiscalWindow:
    """The client's own fiscal window for a tax year, or an flagged assumption.

    The stored rule is one window (the client's base year); later years shift by
    whole years, which is how a repeating fiscal calendar works. A 53-week
    calendar drifts a few days a year and this does not model that — so the
    shifted window is returned only when it still lands on the requested tax
    year under the programme's own convention.
    """
    if account_id is None:
        return assumed_calendar_window(tax_year, convention)

    # Only the lakehouse source holds per-client fiscal rules. Reading them
    # while payroll comes from somewhere else pairs one client's calendar with
    # another source's paychecks — a window that matches neither.
    from tools.fabric_source import active_data_source

    if active_data_source() != "lakehouse":
        return assumed_calendar_window(tax_year, convention)

    rules = _rules_with_overrides(account_id)
    if rules is None:
        return assumed_calendar_window(tax_year, convention)

    for rule in rules:
        window = _window_from_rule(rule, account_id, tax_year, convention)
        if window is not None:
            return window

    return assumed_calendar_window(tax_year, convention)


def _rule_note(rule: Any, account_id: int, begin: date, end: date, shift: int) -> str:
    """Where the window came from, so a reader can tell the client's own rule from an app-owned override."""
    origin = "an app-owned override" if str(rule.name).startswith("override:") else "EntityFiscalYearRules"
    text = f"From {origin} for account {account_id}" + (f" ({rule.rule_expression})" if rule.rule_expression else "")
    if not shift:
        return text + "."
    return f"{text}, shifted {shift:+d} year(s) from the stored base window {begin.isoformat()}..{end.isoformat()}."


def _window_from_rule(rule: Any, account_id: int, tax_year: int, convention: TaxYearLabel) -> FiscalWindow | None:
    """The rule's window shifted onto `tax_year`, or None when it cannot represent that year."""
    begin, end = _as_date(rule.fiscal_year_begin), _as_date(rule.fiscal_year_end)
    if not begin or not end or end < begin:
        return None
    shift = tax_year - (begin.year if convention == "begins" else end.year)
    try:
        shifted_begin, shifted_end = begin.replace(year=begin.year + shift), end.replace(year=end.year + shift)
    except ValueError:  # 29 Feb into a common year
        return None
    return window_from_client_rules(shifted_begin, shifted_end, convention, note=_rule_note(rule, account_id, begin, end, shift))


def fiscal_window_for_state_year(account_id: int | None, state: str, tax_year: int) -> FiscalWindow | None:
    """The client's fiscal window for a state-year, WITH its provenance (`basis`, `assumed`, `note`).

    One resolver for every caller that measures Average Headcount. The assessment and the two what-if simulators each
    took their own view of "the twelve months", and the last time they disagreed Position quoted $0 for a
    client-year while Plan quoted $252,280. It used to hand back bare dates and swallow every exception, so the
    `assumed` flag never reached the claim: a calendar year assumed for a non-calendar filer looked identical to the
    client's own. Only a state with no programme to take a convention from gives None; a typed dependency failure
    (`strict` policy, an unavailable lookup) propagates.
    """
    from tools.credit_math import PROGRAM_CODE_TO_PACK, STATE_TO_PACK, resolve_tax_year_convention

    pack_file = STATE_TO_PACK.get((state or "").upper())
    code = next((c for c, f in PROGRAM_CODE_TO_PACK.items() if f == pack_file), None) if pack_file else None
    if not code:
        return None
    try:
        convention = resolve_tax_year_convention(code, tax_year)
    except (FileNotFoundError, ValueError, KeyError):  # a year with no authored statute has no window
        return None
    return client_fiscal_window(account_id, tax_year, convention["label"])


def window_for_state_year(account_id: int | None, state: str, tax_year: int) -> tuple[date, date] | None:
    """`fiscal_window_for_state_year` as plain dates, for callers that only measure; None as there."""
    window = fiscal_window_for_state_year(account_id, state, tax_year)
    return (window.begin, window.end) if window else None
