"""The Gold read side is a port with two implementations and one adapter package. [RM-19]

`GoldReadPort` (application) is what a handler may depend on. `GoldReader` is the Fabric
Warehouse implementation; `SqliteGoldReader` is the same class with its two execution
hooks pointed at SQLite, which is how the offline suite runs every real statement.
Three things can drift, and each is a test here: an implementation and the port disagreeing
(a read added on one side, a parameter renamed), the old `gold_reader` import path losing a
name its callers use, and a caller reaching past the port to the adapter package.
"""
from __future__ import annotations

import ast
import inspect
import typing
from pathlib import Path

import pytest

from application.gold_read_port import GoldReadPort
from infrastructure.persistence.gold_reader import GoldReader
from tests.data_engine_fixture import CLIENT, YEAR, SqliteGoldReader, SqliteWarehouse

BACKEND = Path(__file__).resolve().parent.parent
PACKAGE = BACKEND / "infrastructure" / "persistence" / "gold_reader"
ADAPTER = "infrastructure.persistence.gold_reader"

#: Outside `bootstrap` and `infrastructure`, the only modules that name the adapter package:
#: operator scripts that open a reader of their own against a live Warehouse.
SCRIPTS_THAT_OPEN_A_READER = {
    "tools/backfill_gold.py": "re-derives the Gold tables a run did not write, against the live Warehouse",
    "tools/verify_unit_filter.py": "one-off proof that the unit filter narrows in SQL, against the live Warehouse",
}


def _port_members() -> dict[str, object]:
    """Every public member the port declares, across the group protocols it is composed from."""
    members: dict[str, object] = {}
    for cls in GoldReadPort.__mro__:
        if cls in (object,) or cls.__name__ in {"Protocol", "Generic"}:
            continue
        for name, value in vars(cls).items():
            if not name.startswith("_") and (callable(value) or isinstance(value, property)):
                members[name] = value
    return members


def _contract(function) -> tuple[list[tuple[str, object]], dict[str, object]]:
    """(required parameters in order, optional parameter -> default) with `self` dropped.

    A port method that carries `**options: Unpack[SomeTypedDict]` declares those keys as
    optional parameters whose defaults live in the adapter (`ANY_DEFAULT`).
    """
    hints = typing.get_type_hints(function)
    required: list[tuple[str, object]] = []
    optional: dict[str, object] = {}
    for p in list(inspect.signature(function).parameters.values())[1:]:
        if p.kind is p.VAR_KEYWORD:
            optional.update(dict.fromkeys(typing.get_args(hints[p.name])[0].__annotations__, ANY_DEFAULT))
        elif p.default is p.empty:
            required.append((p.name, p.kind))
        else:
            optional[p.name] = p.default
    return required, optional


ANY_DEFAULT = object()


def _differences(provided, declared) -> list[str]:
    have, want = _contract(provided), _contract(declared)
    problems = []
    if have[0] != want[0]:
        problems.append(f"required {have[0]} != {want[0]}")
    if set(have[1]) != set(want[1]):
        problems.append(f"optional {sorted(have[1])} != {sorted(want[1])}")
    problems += [
        f"default of {name}: {have[1][name]!r} != {default!r}"
        for name, default in want[1].items()
        if name in have[1] and default is not ANY_DEFAULT and have[1][name] != default
    ]
    return problems


def _public(cls: type) -> set[str]:
    return {
        n for n in dir(cls)
        if not n.startswith("_") and (callable(getattr(cls, n)) or isinstance(inspect.getattr_static(cls, n), property))
    }


IMPLEMENTATIONS = [GoldReader, SqliteGoldReader]


def test_the_port_declares_the_reads_it_is_composed_from():
    names = set(_port_members())
    assert {"latest_run", "unit_page", "unit_drill", "headcount_series", "at_risk", "eligibility_population",
            "employee_drill", "scope", "connection"} <= names
    assert len(names) == 25


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS, ids=lambda c: c.__name__)
def test_an_implementation_provides_every_port_method_with_the_same_parameters(implementation):
    problems = []
    for name, declared in _port_members().items():
        if isinstance(declared, property):
            if not isinstance(inspect.getattr_static(implementation, name, None), property):
                problems.append(f"{name}: not a property")
            continue
        provided = getattr(implementation, name, None)
        if provided is None:
            problems.append(f"{name}: missing")
        else:
            problems += [f"{name}: {d}" for d in _differences(provided, declared)]
    assert not problems, problems


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS, ids=lambda c: c.__name__)
def test_an_implementation_offers_no_public_read_the_port_does_not_declare(implementation):
    assert _public(implementation) - set(_port_members()) == set()


def test_the_offline_reader_answers_not_calculated_for_a_client_nobody_has_run():
    reader: GoldReadPort = SqliteGoldReader(SqliteWarehouse())
    assert reader.latest_run(CLIENT) is None and reader.run_in_flight(CLIENT) is None
    empty = {
        "unit_page": reader.unit_page(CLIENT, method="min_max"),
        "unit_drill": reader.unit_drill(CLIENT, "W", tax_year=YEAR, method="min_max"),
        "headcount": reader.headcount_series(CLIENT, tax_year=YEAR, method="min_max"),
        "series": reader.client_year_series(CLIENT),
        "onezero": reader.onezero_matrix(CLIENT, tax_year=YEAR, method="min_max"),
        "at_risk": reader.at_risk(CLIENT, tax_year=YEAR, method="min_max", min_weekly_hours=1, min_weekly_wages=1),
        "proximity": reader.proximity_candidates(
            CLIENT, tax_year=YEAR, method="min_max", min_weekly_hours=1, min_weekly_wages=1, widest_band_hours=1),
        "eligibility": reader.eligibility_population(CLIENT, tax_year=YEAR, min_weekly_hours=1, min_weekly_wages=1),
        "drill": reader.employee_drill(CLIENT, tax_year=YEAR, record_token="x"),
    }
    assert {name: value["run"] for name, value in empty.items()} == dict.fromkeys(empty)
    assert reader.cohort_periods(CLIENT, tax_year=YEAR, run_id="r", tokens=[]) == {}
    assert reader.unit_years(CLIENT, method="min_max") == ([], 0)


# Every name the old single-file module defined or imported that anything still reaches for.
OLD_MODULE_NAMES = (
    "GoldReader", "run_envelope", "Statement", "UNIT_YEAR_MASTER_COLUMNS", "ELIGIBILITY_SORTS",
    "EMPLOYEE_FILTERS", "NEAR_FILTERS", "GOLD_SCHEMA", "OPS_SCHEMA", "STRANDED_RUN_MINUTES",
    "FabricWarehouseConnection", "_MONEY_COLUMNS", "_BOOL_COLUMNS", "_MANIFEST_COLUMNS", "_MONTH_COLUMNS",
    "_CONNECTION_LOST_STATES", "_EMPLOYEE_SORTS", "_NEAR_SORTS", "_value", "_rows", "_order_by",
    "_near_params", "_eligibility_filter", "_unit_year_where", "_ELIGIBILITY_PIVOT", "_ELIGIBILITY_STATUS",
    "_ELIGIBILITY_NEAR", "_ELIGIBILITY_DRIFT",
    "_stmt_latest_run", "_stmt_run_in_flight", "_stmt_unit_years_count", "_stmt_unit_years",
    "_stmt_month_summaries", "_stmt_credit_columns", "_stmt_unit_totals", "_stmt_unit_lifetime",
    "_stmt_unit_grid", "_stmt_credit_grid", "_stmt_unit", "_stmt_method_summary", "_stmt_month_totals",
    "_stmt_client_year_series", "_stmt_client_year_credit", "_stmt_drill_verdicts", "_stmt_drill_segments",
    "_stmt_drill_periods", "_stmt_cohort_periods", "_stmt_at_risk", "_stmt_at_risk_counts",
    "_stmt_proximity_counts", "_stmt_proximity_candidates", "_stmt_onezero_matrix", "_stmt_unit_fein_summary",
    "_stmt_client_year_rows", "_stmt_eligibility_summary", "_stmt_eligibility_page",
    "_stmt_eligibility_matching", "_stmt_unit_months", "_stmt_unit_employees", "_stmt_unit_near_threshold",
)


def test_the_package_still_exports_every_name_the_single_module_did():
    from infrastructure.persistence import gold_reader

    assert [n for n in OLD_MODULE_NAMES if not hasattr(gold_reader, n)] == []


def _imports(path: Path) -> set[str]:
    """Every module a file imports, as a dotted name; `from a import b` also yields `a.b`."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def _names_the_adapter(imports: set[str]) -> bool:
    return any(name == ADAPTER or name.startswith(ADAPTER + ".") for name in imports)


def test_only_the_composition_root_the_adapters_and_named_scripts_import_the_gold_reader_package():
    offenders = []
    for path in sorted(BACKEND.rglob("*.py")):
        relative = path.relative_to(BACKEND).as_posix()
        if relative.split("/")[0] in {"bootstrap", "infrastructure", "tests", ".venv"} or "__pycache__" in path.parts:
            continue
        if _names_the_adapter(_imports(path)) and relative not in SCRIPTS_THAT_OPEN_A_READER:
            offenders.append(relative)
    assert not offenders, f"depend on application.gold_read_port.GoldReadPort instead: {offenders}"


def test_every_named_script_still_imports_the_package():
    stale = [s for s in SCRIPTS_THAT_OPEN_A_READER if not _names_the_adapter(_imports(BACKEND / s))]
    assert not stale, f"drop these from SCRIPTS_THAT_OPEN_A_READER: {stale}"


def _layer(stem: str) -> int:
    """Dependency order inside the package: columns, then statements, then reads, then the assembled reader."""
    if stem in {"__init__"}:
        return 4
    if stem == "reader":
        return 3
    if stem.startswith("reads_") or stem in {"reader_base"}:
        return 2
    return 1 if stem.startswith("stmt_") or stem == "envelope" else 0


def test_the_package_imports_downward_only():
    problems = []
    for path in sorted(PACKAGE.glob("*.py")):
        for name in _imports(path):
            parts = name.split(".")
            if name.startswith(ADAPTER + ".") and (PACKAGE / f"{parts[3]}.py").exists():
                if _layer(parts[3]) > _layer(path.stem):
                    problems.append(f"{path.name} -> {parts[3]}")
    assert not problems, problems


def test_statement_modules_hold_no_connection_and_no_read_methods():
    """SQL text and parameters only: a statement that opened a connection could not be issued two ways."""
    problems = []
    for path in sorted(PACKAGE.glob("stmt_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        problems += [f"{path.name}: class {n.name}" for n in tree.body if isinstance(n, ast.ClassDef)]
        if "pyodbc" in _imports(path):
            problems.append(f"{path.name}: imports pyodbc")
    assert not problems, problems
