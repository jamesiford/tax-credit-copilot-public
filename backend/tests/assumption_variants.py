"""Make a superseded methodology runnable as a test fixture.

From v8 the engine resolves statutory floors from the year-scoped rule pack and
never from BA-06 [ADR-005]. The published sets v1-v7 predate that seam: they
carry their floor inline and name no programme or tax year, so they are retired
and no longer runnable. See `RETIRED_ASSUMPTION_SETS` in `tools.reference_source`.

Several tests, however, are not about *replay* at all — they pin the behaviour
of one measurement decision (BA-02's boundary rule, BA-12's short-period filter,
BA-03's denominator mode), and they used a published set as a convenient
pre-built combination of those flags. That coverage is worth keeping.

This module rebuilds those combinations as throwaway fixtures. Each one is the
historical set's *methodology*, plus the `program_code`/`tax_year` the new seam
needs — with the year chosen so the pack's floor equals the floor that set
carried inline. The arithmetic is therefore unchanged, and a test that asserted
a count under v3 asserts the same count now.

    from assumption_variants import runnable_set

    path = runnable_set("v3", tmp_path)
    snapshot = TccPayrollAdapter(source_dir=src, assumption_path=path).scan()

Registration is process-global, so `restore_assumption_registries` in conftest
is autouse and undoes it after every test.

The historical sets live in `tests/fixtures/assumption_sets/` rather than in
`docs/`. They were once published documents, but nothing reads them as
documentation any more — they exist so a superseded measurement decision stays
executable, which makes them test fixtures. Keeping them beside the tests means
a docs reorganisation cannot silently break the suite, which is exactly what
happened when they lived under `docs/data/`.
"""
from __future__ import annotations

import json
from pathlib import Path

from tools import reference_onezero, reference_source

_FIXTURES = Path(__file__).resolve().parents[1] / "rules" / "methodology"

_PROGRAM_CODE = "GA_JTC"

# Which tax year's rule pack reproduces the floor a historical set held inline.
# GA's weekly floor tracks its lowest-wage county, so the $686 the v3/v4 era used
# is not a wrong number — it is Georgia's TY2024 figure, and resolving those sets
# against the 2024 pack yields exactly what they always yielded.
_TAX_YEAR_FOR_WAGE_FLOOR = {
    636.0: 2023,
    686.0: 2024,
}

# The one/zero set each historical step-1 set was paired with. The one/zero axis
# holds no statutory values, so these files need no modification — only
# re-registration.
_ONEZERO_FOR_STEP1 = {
    "GDS-STEP1-2026-07-29-v1": "GDS-ONEZERO-2026-07-29-v1",
    "GDS-STEP1-2026-07-29-v2": "GDS-ONEZERO-2026-07-29-v2",
    "GDS-STEP1-2026-07-29-v3": "GDS-ONEZERO-2026-07-29-v3",
    "GDS-STEP1-2026-07-30-v4": "GDS-ONEZERO-2026-07-30-v4",
    "GDS-STEP1-2026-08-05-v5": "GDS-ONEZERO-2026-08-05-v5",
    "GDS-STEP1-2026-08-18-v6": "GDS-ONEZERO-2026-08-18-v6",
    "GDS-STEP1-2026-08-24-v7": "GDS-ONEZERO-2026-08-24-v7",
}


def runnable_set(version: str, tmp_dir: Path) -> Path:
    """Return a runnable copy of `reference-dataset-assumptions.<version>.json`.

    Registers it (and its paired one/zero set) with the engine for the duration
    of the test. The published document on disk is never modified.
    """
    source = _FIXTURES / f"reference-dataset-assumptions.{version}.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    set_id = payload["assumption_set_id"]

    if "program_code" not in payload:
        floor = payload["assumptions"]["BA-06"]["config"].get(
            "minimum_average_weekly_wages_usd"
        )
        try:
            tax_year = _TAX_YEAR_FOR_WAGE_FLOOR[float(floor)]
        except (KeyError, TypeError) as exc:
            raise AssertionError(
                f"{version} carries an inline wage floor of {floor!r} with no year "
                f"pack that reproduces it. Add the year to _TAX_YEAR_FOR_WAGE_FLOOR "
                f"or author the pack — do not adjust the floor to make a test pass."
            ) from exc
        payload["program_code"] = _PROGRAM_CODE
        payload["tax_year"] = tax_year

    target = tmp_dir / f"assumptions.{version}.runnable.json"
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    reference_source._ASSUMPTION_PATHS[set_id] = target
    reference_source._ASSUMPTION_COUNTS[set_id] = len(payload["assumptions"])

    onezero_id = _ONEZERO_FOR_STEP1.get(set_id)
    if onezero_id:
        reference_onezero.STEP1_TO_ONEZERO[set_id] = onezero_id
        reference_onezero._ASSUMPTION_PATHS.setdefault(
            onezero_id,
            _FIXTURES / f"reference-onezero-assumptions.{version}.json",
        )

    return target
