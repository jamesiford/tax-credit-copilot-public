"""The lookup resolver: the only way code reads an app-owned lookup. [07]

Provider order `source -> override -> seed -> default -> none`, with a per-lookup policy. Pay codes are the
highest risk: an unmapped code is dropped by a state's whitelist BEFORE the calculation runs, so eligibility
reads zero with no error. So the resolver reports every code it could not map, and under `strict` an unmapped
code blocks the calculation with a message that lists the codes.

Policy defaults: pay codes are `strict` for customer-classified data (the seed is a convention for generated
data, not a customer's pay-code list) and `assume` otherwise; fiscal rules are `assume` (a calendar year,
flagged) unless set `strict`. Neither is ever assumed silently.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from config import get_settings

from . import store as overrides
from .model import ASSUME, SPECS, STRICT, PayCodeReport, Provenance
from .seeds import load_seed


def customer_environment() -> bool:
    return get_settings().runtime.data_classification == "customer"


def pay_code_policy() -> str:
    return get_settings().source_model.pay_code_policy or (STRICT if customer_environment() else ASSUME)


def fiscal_rules_policy() -> str:
    return get_settings().source_model.fiscal_rules_policy or ASSUME


def _norm(code: Any) -> str:
    return str(code).strip().upper()


class PayCodeResolver:
    """Maps one account's pay codes to the canonical categories the rule packs name; most specific match wins."""

    def __init__(self, account_id: int, policy: str | None = None, today: date | None = None) -> None:
        self.policy = policy or pay_code_policy()
        store, day = overrides.get_store(), today or date.today()
        entries = [e for e in (store.entries("pay_code_category", account_id) if store else []) if e.active_on(day)]
        self._override = {(e.client_id == overrides.GLOBAL_CLIENT, e.key_kind, e.key): e for e in entries}
        self._account = account_id
        seed = load_seed("pay_code_category")
        # The seed is a convention for generated data. Under `strict` on customer data it is not a source of truth.
        self._seed = seed if seed and (self.policy == ASSUME or not customer_environment()) else None

    def resolve(self, code: str | None, category_id: Any = None) -> tuple[str | None, str, bool]:
        """(canonical, provider, inferred); canonical is None when nothing maps the code."""
        text = _norm(code) if code else ""
        for is_global in (False, True):
            for kind, key in (("code", text), ("category", str(category_id) if category_id is not None else "")):
                found = self._override.get((is_global, kind, key)) if key else None
                if found is not None:
                    return found.value, "override", found.inferred
        if self._seed is not None and text in self._seed.entries:
            return self._seed.entries[text], "seed", self._seed.inferred
        return None, "none", False

    def provenance(self) -> Provenance:
        store = overrides.get_store()
        if self._override:
            return Provenance("pay_code_category", "override", rows=len(self._override), policy=self.policy)
        if self._seed is not None:
            return Provenance("pay_code_category", "seed", str(self._seed.version), self._seed.inferred, policy=self.policy)
        return Provenance("pay_code_category", "none", policy=self.policy, note="no override and no usable seed" + ("" if store else "; no override store"))


def resolve_pay_codes(dataset: Any, policy: str | None = None) -> tuple[dict[Any, str | None], PayCodeReport]:
    """Canonical category per `pay_code_id` (None = unmapped), and the report of what that cost."""
    resolver = PayCodeResolver(dataset.account.account_id, policy)
    rows_by_id: dict[Any, int] = {}
    for p in dataset.payroll:
        rows_by_id[p.pay_code_id] = rows_by_id.get(p.pay_code_id, 0) + 1
    resolved: dict[Any, str | None] = {None: None}
    unmapped: dict[str, int] = {}
    providers: dict[str, int] = {}
    inferred = 0
    for code in dataset.pay_codes:
        canonical, provider, was_inferred = resolver.resolve(code.pay_code, code.pay_code_category_id)
        resolved[code.pay_code_id] = canonical
        providers[provider] = providers.get(provider, 0) + 1
        inferred += was_inferred
        if canonical is None and rows_by_id.get(code.pay_code_id, 0):
            unmapped[(code.pay_code or "").strip() or f"<id {code.pay_code_id}>"] = rows_by_id.get(code.pay_code_id, 0)
    report = PayCodeReport(
        resolver.policy, len(dataset.pay_codes), tuple(sorted(unmapped)), sum(unmapped.values()), inferred, providers,
        null_code_rows=sum(n for key, n in rows_by_id.items() if key is None or key not in resolved),
    )
    return resolved, report


def fiscal_override_rules(account_id: int) -> list[Any]:
    """Override-layer fiscal rules for a client (or its global default), as `EntityFiscalYearRules`-shaped rows."""
    from data.source.schema import EntityFiscalYearRules

    store, day, out = overrides.get_store(), date.today(), []
    for entry in (store.entries("entity_fiscal_year_rules", account_id) if store else []):
        if entry.key_kind != "rule" or not entry.active_on(day):
            continue
        value = json.loads(entry.value)
        out.append((entry.client_id == overrides.GLOBAL_CLIENT, EntityFiscalYearRules(
            fiscal_year_rules_id=-1, name=f"override:{entry.key}", fiscal_year_begin=date.fromisoformat(value["fiscal_year_begin"]),
            fiscal_year_end=date.fromisoformat(value["fiscal_year_end"]), rule_expression=value.get("rule_expression"),
            inferred=entry.inferred,
        )))
    return [rule for _, rule in sorted(out, key=lambda pair: pair[0])]  # a client's own rule before the global default


def lookup_status(source_tables: dict[str, bool] | None = None, account_id: int | None = None) -> list[dict[str, Any]]:
    """Every lookup with its provider and what it affects, for the startup log and the validation report.

    `source_tables` maps a lookup to whether the customer's lake carries its table (None when unknown).
    """
    from data.source.industry import industry_provenance

    pay = PayCodeResolver(account_id or overrides.GLOBAL_CLIENT).provenance()
    present = source_tables or {}
    fiscal = ("source" if present.get("entity_fiscal_year_rules") else
              "override" if account_id is not None and fiscal_override_rules(account_id) else "none")
    entries = [
        pay,
        Provenance("entity_fiscal_year_rules", fiscal, policy=fiscal_rules_policy()),
        Provenance("pay_frequency", "default", note="label derived from the measured period span"),
        industry_provenance(),
    ]
    return [{**p.as_dict(), "status": p.label, "affects": SPECS[p.lookup].used_for,
             "statute_affecting": SPECS[p.lookup].statute_affecting,
             "if_missing": SPECS[p.lookup].if_missing if p.provider == "none" else ""} for p in entries]
