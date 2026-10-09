"""The two Fabric sources are not interchangeable, and confusing them is silent.

`DATA_SOURCE=fabric` reads a flattened single-tenant `employees` table — 9,477
rows, 305 employees, no account column. `DATA_SOURCE=lakehouse` reads the
customer's source schema across five accounts and 564,931 rows, including the
reference dataset client.

Pointing at the wrong one does not raise. The app starts, one client resolves,
and every portfolio view is simply thin — which is how the demo ran for a day
against 3% of the data without anything looking broken.

These tests pin the distinction so it cannot be re-lost, and skip cleanly when
Fabric is unreachable rather than failing a local run.
"""
from __future__ import annotations

import os

import pytest

from tests.certified import (
    CERTIFIED_EMPLOYEES,
    CERTIFIED_MIN_MAX_ELIGIBLE,
    CERTIFIED_PAY_PERIOD_ELIGIBLE,
    FISCAL_WINDOW,
)

REFERENCE_ACCOUNT = 1001
EXPECTED_ACCOUNTS = {1001, 2001, 2002, 2003, 2004}


def _lakehouse_or_skip():
    """The lakehouse reader, or a skip naming the reason.

    A paused Fabric capacity reports `ArtifactNotFound`, which reads exactly like
    a missing lakehouse — so the skip message says so, rather than leaving the
    next person to rediscover it.
    """
    if os.getenv("TCC_FABRIC_TESTS") != "1":
        pytest.skip("set TCC_FABRIC_TESTS=1 to run tests that reach live Fabric")
    try:
        from data.source.from_fabric import FabricLakehouseReader

        reader = FabricLakehouseReader()
        reader.list_accounts()
        return reader
    except Exception as exc:  # noqa: BLE001 — the reason matters more than the type
        pytest.skip(
            f"Fabric unreachable ({type(exc).__name__}). If this is "
            f"ArtifactNotFound, check the capacity is Active before assuming the "
            f"lakehouse is missing: {exc}"
        )


def test_lakehouse_carries_every_account():
    reader = _lakehouse_or_skip()
    found = {int(a["AccountId"]) for a in reader.list_accounts()}
    assert EXPECTED_ACCOUNTS <= found, (
        f"the lakehouse should expose all five demo accounts; missing "
        f"{sorted(EXPECTED_ACCOUNTS - found)}"
    )


def test_lakehouse_carries_the_whole_reference_client():
    """3% of the rows is the failure mode this catches.

    The flattened `employees` table has 9,477 rows. If a config change silently
    repoints the lakehouse reader at it, this is the assertion that notices.
    """
    reader = _lakehouse_or_skip()
    rows = reader.bcs_rows(REFERENCE_ACCOUNT)
    assert len(rows) == 384_433, (
        f"reference client should have 384,433 rows, got {len(rows):,}. "
        f"9,477 means something is reading the flattened `dbo/employees` table."
    )
    assert len({r["Employee_ID"] for r in rows}) == CERTIFIED_EMPLOYEES


def test_lakehouse_reproduces_the_certified_figures():
    """The certified run must survive the journey through Fabric.

    Same 10,236 / 539 / 656 the CSV path produces. If reading from the source
    schema moved them, the projection is lossy and nothing downstream is safe.
    """
    reader = _lakehouse_or_skip()
    from config import get_fiscal_year_end_month
    from tools.credit_math import load_pack_one_zero
    from domain.calculation.onezero import run_min_max_method, run_pay_period_method

    rows = reader.bcs_rows(REFERENCE_ACCOUNT)
    common = dict(
        tax_year=2023,
        analysis_start_month=FISCAL_WINDOW[0],
        pack=load_pack_one_zero("GA", tax_year=2023),
        fiscal_year_end_month=get_fiscal_year_end_month(),
        fiscal_window=FISCAL_WINDOW,
    )
    min_max = run_min_max_method(rows, **common)
    pay_period = run_pay_period_method(rows, **common)

    assert len(min_max.total_hours_and_wages) == CERTIFIED_EMPLOYEES
    assert len(min_max.eligible_employees) == CERTIFIED_MIN_MAX_ELIGIBLE
    assert len(pay_period.eligible_employees) == CERTIFIED_PAY_PERIOD_ELIGIBLE


def test_synthetic_clients_span_the_retroactive_window():
    """Six years of payroll is what makes a retroactive audit demonstrable."""
    reader = _lakehouse_or_skip()
    for account_id in sorted(EXPECTED_ACCOUNTS - {REFERENCE_ACCOUNT}):
        rows = reader.bcs_rows(account_id)
        years = {int(str(r["Pay_Date"])[:4]) for r in rows}
        assert len(years) >= 6, (
            f"account {account_id} spans only {sorted(years)}; the retroactive "
            f"story needs at least six years"
        )


def test_the_flattened_source_is_a_different_shape():
    """Documents WHY the two are not interchangeable, so the next person sees it.

    The flattened table has no account column at all, which is the root reason it
    cannot serve portfolio scope — not merely that it holds fewer rows.
    """
    if os.getenv("TCC_FABRIC_TESTS") != "1":
        pytest.skip("set TCC_FABRIC_TESTS=1 to run tests that reach live Fabric")
    from tools.fabric_source import FabricEmployeesAdapter

    try:
        raw = FabricEmployeesAdapter(
            workspace="partner-tax-credit-demo",
            lakehouse="partner_tax_credit_demo_lakehouse",
        )._fetch_raw()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"flattened table unreachable: {exc}")

    assert raw, "flattened employees table is empty"
    columns = set(raw[0])
    assert not (columns & {"AccountId", "Account_ID", "ClientId"}), (
        "the flattened table gained an account column; if it is now multi-tenant "
        "this test and the .env.example guidance both need revisiting"
    )


def test_the_reader_waits_out_a_slow_connect(monkeypatch):
    """Losing these options degrades into intermittent 500s, not a failure here.

    OneLake on this capacity takes tens of seconds to accept a connection for a
    tiny Delta log — measured at 13s, 22s, 13s, 38s and 29s on five consecutive
    opens, while the front door answers an unauthenticated GET for the same URL
    in 0.7s. `object_store` defaults to a 5s connect timeout, so it abandons
    connections that are alive but slow, retries them, and eventually gives up —
    surfacing as "operation timed out ... after 10 retries" on every read path at
    once, while the capacity is Active and the network is fine.

    Needs no lakehouse: the options are assembled before anything is opened.
    """
    import data.source.from_fabric as mod

    monkeypatch.setattr(mod, "_storage_token", lambda: "fake-token")
    options = mod.FabricLakehouseReader(workspace="w", lakehouse="l")._storage_options()

    assert options["connect_timeout"] == "60s", (
        "the 5s object_store default is what turns slow OneLake into a 500"
    )
    assert int(options["max_retries"]) <= 3, (
        "retrying a slow-but-alive connect ten times adds load to the thing "
        "already struggling"
    )
    assert options["bearer_token"] == "fake-token", (
        "transport options must merge alongside auth, not replace it"
    )
