"""Shared skip guard for tests exercising the One/Zero reference benchmark.

`stakeholder-docs/` held the partner's own source documents (a methodology
workbook and a historical wages PDF) that
`tools.reference_onezero.run_reference_onezero` hashes into its provenance.
B05 removed that directory from the repository for good — unlike the private
payroll extract (`backend/data/payroll/`, gitignored but re-stageable for a
private reconciliation run), there is no workflow in which these two files
come back. So this is a plain, permanent skip, not a `TCC_REQUIRE_PARITY`
condition: nothing should ever expect them to be present again.

Import `pytestmark` from this module into any test module that calls
`run_reference_onezero` (directly or via `ReferenceWorkspaceService`), so
there is exactly one definition of the condition.

This module is deliberately not named `test_*`, so pytest does not collect it.
"""
from __future__ import annotations

import pytest

from tools.reference_onezero import methodology_sources_present

pytestmark = pytest.mark.skipif(
    not methodology_sources_present(),
    reason=(
        "stakeholder-docs/ was removed from the repository (B05); the "
        "methodology workbook and historical wages PDF this benchmark hashes "
        "into its provenance no longer exist anywhere to stage."
    ),
)
