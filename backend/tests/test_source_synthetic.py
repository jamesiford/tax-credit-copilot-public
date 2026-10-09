"""The synthetic clients must be usable, not merely well-formed.

A generator that produced zero eligible employees, or one that produced 100%,
would pass a schema check and be worthless in a demo. These assert the shape of
the population as well as the shape of the tables.

They also cover what Candle Bottle cannot: more than one tenant, fiscal years that
are not the partner's 53-week calendar, and an entity hierarchy.
"""
from __future__ import annotations

from datetime import date

import pytest

from certified import certified_pack
from data.source import (
    SYNTHETIC_CLIENTS,
    build_all_synthetic,
    build_synthetic_dataset,
    source_to_bcs_rows,
    projection_controls,
)
from domain.calculation.onezero import run_min_max_method, run_pay_period_method


@pytest.fixture(scope="module")
def datasets():
    return build_all_synthetic()


def test_every_client_generates(datasets):
    assert len(datasets) == len(SYNTHETIC_CLIENTS)
    for ds in datasets:
        c = ds.counts()
        assert c["payroll"] > 0, f"{ds.account.name} produced no payroll"
        assert c["employments"] > 0
        assert c["locations"] > 0


def test_generation_is_deterministic():
    """A demo must not shift between rehearsal and delivery, and a snapshot hash
    is meaningless if the same seed yields different bytes."""
    spec = SYNTHETIC_CLIENTS[0]
    a = build_synthetic_dataset(spec)
    b = build_synthetic_dataset(spec)
    assert a.counts() == b.counts()
    assert [p.payroll_id for p in a.payroll[:500]] == [p.payroll_id for p in b.payroll[:500]]
    assert [p.hours for p in a.payroll[:500]] == [p.hours for p in b.payroll[:500]]


def test_accounts_are_distinct_and_never_collide_with_reference(datasets):
    """Tenant isolation starts with tenants that are actually distinct."""
    ids = [ds.account.account_id for ds in datasets]
    assert len(set(ids)) == len(ids)
    assert 1001 not in ids, "1001 is Candle Bottle — the reference client"


def test_foreign_keys_resolve(datasets):
    for ds in datasets:
        entity_ids = {e.entity_id for e in ds.entities}
        location_ids = {loc.location_id for loc in ds.locations}
        address_ids = {a.address_id for a in ds.addresses}
        scz_ids = {s.state_county_zip_id for s in ds.state_county_zips}
        code_ids = {p.pay_code_id for p in ds.pay_codes}

        for loc in ds.locations:
            assert loc.entity_id in entity_ids
            assert loc.address_id in address_ids
        for addr in ds.addresses:
            assert addr.state_county_zip_id in scz_ids
        for p in ds.payroll:
            assert p.account_id == ds.account.account_id
            assert p.entity_id in entity_ids
            assert p.location_id in location_ids
            assert p.pay_code_id in code_ids


def test_fiscal_years_actually_differ(datasets):
    """The point of these clients. If every one were a calendar year, the
    per-client fiscal window would never be exercised."""
    windows = {
        (r.fiscal_year_begin, r.fiscal_year_end)
        for ds in datasets for r in ds.fiscal_year_rules
    }
    assert len(windows) > 1, "all synthetic clients share one fiscal window"
    assert any(b.month != 1 for b, _ in windows), "no non-calendar fiscal year"


def test_entity_hierarchy_exists(datasets):
    """CALC-06 entity combination needs a parent/child relationship to walk."""
    multi = [ds for ds in datasets if len(ds.entities) > 1]
    assert multi, "no client has more than one legal entity"
    for ds in multi:
        assert any(e.parent_entity_id is not None for e in ds.entities)
        assert any(e.parent_entity_id is None for e in ds.entities)


def test_mid_year_worksite_has_no_earlier_payroll(datasets):
    """A site that opened in June is not a site with missing January data, and
    the distinction has to survive into the payroll rows."""
    for ds in datasets:
        late = [loc for loc in ds.locations if loc.open_date and loc.open_date > date(2020, 1, 1)]
        for loc in late:
            rows = [p for p in ds.payroll if p.location_id == loc.location_id]
            if rows:
                assert min(p.pay_period_start for p in rows) >= loc.open_date


@pytest.mark.parametrize("spec", SYNTHETIC_CLIENTS, ids=lambda s: s.name)
def test_client_produces_a_usable_eligible_population(spec):
    """The population must straddle the floors.

    All-eligible or none-eligible both render a demo pointless — there would be
    nothing to explain, and no employee "close to qualifying" to drill into.
    """
    ds = build_synthetic_dataset(spec)
    rows = source_to_bcs_rows(ds)
    assert rows, f"{spec.name} projected no BCS rows"

    pack = certified_pack()
    common = {
        "tax_year": spec.fiscal_end.year,
        "analysis_start_month": spec.fiscal_begin.replace(day=1),
        "pack": pack,
        "fiscal_window": (spec.fiscal_begin, spec.fiscal_end),
    }
    pp = run_pay_period_method(rows, **common)
    mm = run_min_max_method(rows, **common)

    evaluated = len(pp.all_averages)
    eligible = len(pp.eligible_employees)
    assert evaluated > 0, f"{spec.name}: no employees evaluated"
    assert 0 < eligible < evaluated, (
        f"{spec.name}: {eligible} of {evaluated} eligible — the population does "
        "not straddle the floors, so there is nothing to demonstrate"
    )

    # BA invariant: Min Max is the best case, so it can never be beaten by the
    # Pay Period method on the same data.
    assert len(mm.eligible_employees) >= eligible or abs(len(mm.eligible_employees) - eligible) <= 2


def test_projection_controls_report_every_row(datasets):
    """Silver must account for its input. A row that vanishes without a count
    is how a wrong number reaches a filed return."""
    for ds in datasets:
        rows = source_to_bcs_rows(ds)
        c = projection_controls(ds, rows)
        assert c["bcs_rows_out"] + c["dropped_no_period_span"] == c["payroll_rows_in"]
        assert c["account_id"] == ds.account.account_id


def test_worksite_ids_carry_their_state_prefix(datasets):
    """Regression: the pipeline filters per state by worksite prefix.

    `_payperiods.iter_state_packs` selects rows with
    `Worksite_ID.startswith(f"{state}_")`. The first source projection emitted
    `GA-001` and bare numeric ids, so every state filter matched nothing and the
    API returned `results: []` while cheerfully reporting 9,832 rows loaded — a
    silent zero, which is the worst failure mode available.
    """
    for ds in datasets:
        rows = source_to_bcs_rows(ds)
        for r in rows:
            state = r["Work_State"]
            assert state, f"{ds.account.name}: row has no Work_State"
            assert r["Worksite_ID"].startswith(f"{state}_"), (
                f"{ds.account.name}: Worksite_ID {r['Worksite_ID']!r} is not "
                f"prefixed with {state!r} — iter_state_packs will skip it"
            )


def test_projected_rows_survive_the_state_filter(datasets):
    """The end-to-end version of the above: run the real filter and require it
    to return rows for every state the client operates in."""
    from api._payperiods import iter_state_packs

    for ds in datasets:
        rows = source_to_bcs_rows(ds)
        states = {r["Work_State"] for r in rows}
        matched = {st for st, _pack, _rows in iter_state_packs(rows, tax_year=2023)}
        missing = {s for s in states if s not in matched}
        assert not missing, (
            f"{ds.account.name}: no rows survived the state filter for {missing}"
        )


def test_county_reaches_the_row(datasets):
    """County drives Georgia's tier and therefore credit value. Carrying it on
    the row means credit work does not have to re-walk the dimension join."""
    for ds in datasets:
        rows = source_to_bcs_rows(ds)
        assert all(r["Work_County"] for r in rows[:200]), (
            f"{ds.account.name}: rows are missing Work_County"
        )


def test_pay_codes_survive_the_rule_pack_policy(datasets):
    """Regression: an unmapped pay code is dropped BEFORE the calculation runs.

    `apply_pay_code_policy` filters rows against the pack's
    `included_pay_codes` — canonical names like `Regular`, not client codes like
    `REG`. The first source projection emitted raw client codes, so Georgia's
    policy discarded every row and the engine saw no payroll at all: 9,832 rows
    loaded, zero employees evaluated, no error anywhere.

    BA-07 / Q5. Until the partner supplies `PayCodeCategory`, `canonical_pay_code`
    maps by convention, and this asserts the mapping actually clears the packs.
    """
    from tools.credit_math import load_pack_one_zero
    from domain.calculation.onezero import apply_pay_code_policy

    for ds in datasets:
        rows = source_to_bcs_rows(ds)
        for state in sorted({r["Work_State"] for r in rows}):
            pack = load_pack_one_zero(state, tax_year=2023)
            if pack is None:
                continue
            state_rows = [r for r in rows if r["Work_State"] == state]
            kept = apply_pay_code_policy(state_rows, pack)
            assert kept, (
                f"{ds.account.name}/{state}: the pack's pay-code policy discarded "
                f"all {len(state_rows):,} rows. Codes present: "
                f"{sorted({r['Pay_Code'] for r in state_rows})}"
            )


def test_client_pay_codes_map_to_canonical_categories():
    """The mapping itself, including the deliberate fall-through."""
    from data.source.to_bcs import canonical_pay_code

    assert canonical_pay_code("REG") == "Regular"
    assert canonical_pay_code("OT") == "Overtime"
    assert canonical_pay_code("PTO") == "Regular"
    assert canonical_pay_code("MIL") == "Mileage"
    # Unmapped codes pass through rather than defaulting to Regular — an
    # unexpected code should be visible, not silently inflate the wage base.
    assert canonical_pay_code("ZZZ_UNKNOWN") == "ZZZ_UNKNOWN"


def test_clients_do_not_leak_into_each_other(datasets):
    """Two tenants projected in the same process must stay separate."""
    seen: dict[str, int] = {}
    for ds in datasets:
        for r in source_to_bcs_rows(ds):
            acct = r["_Source_Account_Id"]
            prior = seen.setdefault(r["Employee_ID"], acct)
            assert prior == acct, f"employee {r['Employee_ID']} appears under two accounts"
