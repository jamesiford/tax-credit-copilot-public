"""Every payroll-reading endpoint must honour `account_id`.

The bug this guards against was live and silent: `/api/onezero/{year}` accepted
an `account_id` query param, FastAPI discarded it as unknown, and the endpoint
answered with the configured tenant's payroll. Asking for account 2004 returned
account 1001's Average Headcount — byte-identical responses for two different
companies — and the UI rendered it under account 2004's name.

That is the precise error `load_pay_periods` was written to refuse (see its
docstring: "a caller asking for client 42 would receive client 1001's payroll
and could go on to compute, or record, figures for the wrong company"). The
refusal only works if the routers actually pass the argument down.

The suite runs on the single-tenant `csv` source, so the property asserted here
is the one that holds under ANY source: a tenant the source does not hold must
produce a 404, never a different tenant's figures. Under `lakehouse` the same
plumbing carries a real account id through to a real partition.
"""
from __future__ import annotations

import pytest

from infrastructure.payroll.pay_period_source import configured_account_id

# A tenant no data source holds. Chosen well outside the lakehouse account range
# (1001, 2001-2004) so this stays meaningful if the suite is ever pointed at
# the lakehouse.
ABSENT_TENANT = 999_999


def _paths(tax_year: int = 2025) -> list[str]:
    """Every GET that reads payroll and therefore must be tenant-scoped."""
    return [
        f"/api/onezero/{tax_year}",
        f"/api/ingestion/{tax_year}",
        f"/api/ingestion/{tax_year}/rows",
        f"/api/qc/{tax_year}",
        f"/api/forecast/{tax_year}",
        f"/api/alerts/monthly/{tax_year}",
        f"/api/performance/{tax_year}",
        f"/api/reconcile/{tax_year}",
        "/api/onezero/retroactive/scan",
        "/api/triggers",
    ]


@pytest.mark.parametrize("path", _paths())
def test_absent_tenant_is_refused_not_substituted(client, path):
    """An unknown tenant must 404 — not quietly answer as the configured one."""
    response = client.get(path, params={"account_id": ABSENT_TENANT})

    assert response.status_code == 404, (
        f"{path} answered {response.status_code} for a tenant the source does "
        f"not hold. If this is 200, the endpoint dropped account_id and served "
        f"tenant {configured_account_id()}'s payroll under another client's id."
    )


@pytest.mark.parametrize("path", _paths())
def test_configured_tenant_matches_the_unscoped_default(client, path):
    """Naming the configured tenant explicitly must not change the answer.

    Guards the other direction: threading the parameter through must not have
    altered what a single-tenant caller already sees.
    """
    unscoped = client.get(path)
    scoped = client.get(path, params={"account_id": configured_account_id()})

    assert unscoped.status_code == scoped.status_code
    if unscoped.status_code == 200:
        assert unscoped.json() == scoped.json(), (
            f"{path} disagrees with itself when the default tenant is named "
            f"explicitly."
        )


def test_workspace_is_tenant_scoped(client):
    """The portfolio endpoint carries the client's identity, so it matters most."""
    unscoped = client.get("/api/scope")
    scoped = client.get("/api/scope", params={"account_id": configured_account_id()})
    assert unscoped.status_code == 200
    assert scoped.status_code == 200
    assert scoped.json() == unscoped.json()


def test_employee_drill_is_tenant_scoped(client):
    """A per-employee drill under the wrong tenant is a privacy failure, not a 200."""
    response = client.get(
        f"/api/onezero/2025/employee/E00001",
        params={"account_id": ABSENT_TENANT},
    )
    assert response.status_code == 404
