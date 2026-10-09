"""The seam: the reference client read from the lakehouse must be the same client.

`test_source_roundtrip.py` proves the PROJECTION is lossless in memory. This
proves the thing the portal actually does — build the sealed workspace from
Fabric — reproduces the certified result end to end.

Until this existed, the sealed views read four local CSVs while every other
view read the source schema, so one client resolved from two sources on one
screen.

Reaches live Fabric. Set `TCC_FABRIC_TESTS=1` to run it; it skips otherwise, so
CI never needs a lakehouse.
"""
from __future__ import annotations

import os

import pytest

from certified import (
    CERTIFIED_EMPLOYEES,
    CERTIFIED_MIN_MAX_ELIGIBLE,
    CERTIFIED_PAY_PERIOD_ELIGIBLE,
)
from tools.reference_source import CertifiedFiguresMismatch, LakehousePayrollAdapter
from tools.reference_workspace import ReferenceWorkspaceService, _observed_figures

pytestmark = pytest.mark.skipif(
    os.environ.get("TCC_FABRIC_TESTS", "").strip().lower() not in {"1", "true", "yes"},
    reason="set TCC_FABRIC_TESTS=1 to run tests that reach live Fabric",
)


@pytest.fixture(scope="module")
def lakehouse_state():
    return ReferenceWorkspaceService(source_kind="lakehouse").get(force=True)


def test_lakehouse_sourced_workspace_reproduces_the_certified_result(lakehouse_state):
    assert _observed_figures(lakehouse_state.step1) == {
        "employees_evaluated": CERTIFIED_EMPLOYEES,
        "min_max_eligible": CERTIFIED_MIN_MAX_ELIGIBLE,
        "pay_period_eligible": CERTIFIED_PAY_PERIOD_ELIGIBLE,
    }


def test_the_run_declares_where_it_came_from(lakehouse_state):
    """A viewer must never have to guess which source produced a figure."""
    assert lakehouse_state.snapshot.source_kind == "lakehouse"
    assert lakehouse_state.equivalence["matches"] is True
    assert lakehouse_state.equivalence["source_kind"] == "lakehouse"


def test_the_manifest_carries_delta_lineage(lakehouse_state):
    """A Delta version is this path's equivalent of the CSV file hash."""
    from config import SOURCE_SCHEMA

    manifest = lakehouse_state.snapshot.files[0]
    assert manifest.sha256.startswith("sha256:")
    assert manifest.lineage["kind"] == "delta"
    assert manifest.lineage["table"] == f"{SOURCE_SCHEMA}.Payroll"
    assert isinstance(manifest.lineage["version"], int)


def test_source_controls_survive_the_projection(lakehouse_state):
    controls = lakehouse_state.snapshot.controls
    assert controls.distinct_employees == CERTIFIED_EMPLOYEES
    assert controls.distinct_feins == 2
    assert controls.usable_rows > 0


def test_a_source_that_is_not_the_reference_client_is_refused():
    """The gate must fire on a real mismatch, not merely exist.

    A synthetic tenant is a well-formed source-schema account that is
    emphatically not the reference dataset; serving it under the certified
    banner is the exact failure this gate is for.
    """
    service = ReferenceWorkspaceService(source_kind="lakehouse")
    service._adapter = lambda: LakehousePayrollAdapter(account_id=2001)
    with pytest.raises(CertifiedFiguresMismatch):
        service.get(force=True)


def test_missing_account_names_the_problem():
    with pytest.raises(FileNotFoundError, match="not found"):
        LakehousePayrollAdapter(account_id=999_999).scan()
