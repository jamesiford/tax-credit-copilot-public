"""Routers translate HTTP and call the mediator; they name no adapter. [RM-18, ADR-003]

`api/` is the presentation ring. A route builds a request, sends it through the
mediator (Authorization -> Validation -> Handler -> Audit for a write) and maps the
failure types a handler raises onto status codes. Before RM-18 eight routers imported
`infrastructure` directly, one was an application service filed under `api/` because the
payroll reader it needed raised `HTTPException`, and the One/Zero route was 240 lines of
statutory arrangement inside a function. These rules keep that from coming back:

* no module under `api/` imports `infrastructure` or `bootstrap`; a router asks for a
  collaborator through `application.services`, which the composition root fills;
* nothing in `application`, `domain`, `infrastructure`, `tools` or `bootstrap` imports
  `api`, in any import form (the old allowance for `api._assess` is gone);
* a function under `api/` meets the length standard, except a pinned list of named
  legacy functions that may only shrink;
* the routers this package made thin import no statutory math (`tools`, `data`, `config`),
  every route in them reaches the mediator, and the remaining routers may not widen
  what they import from those packages.
"""
from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pytest

from tools.code_standards.metrics import LIMITS, measure

BACKEND = Path(__file__).resolve().parent.parent
API = BACKEND / "api"

#: `module -> {imported package: why}`. Empty on purpose: a router that needs an adapter
#: asks `application.services`, and a read model it needs goes behind a port
#: (`application/gold_ports.py`). Adding an entry is the decision that it may not.
ROUTER_IMPORT_ALLOWANCE: dict[str, dict[str, str]] = {}

_OUTWARD = ("infrastructure", "bootstrap")
_STATUTORY = ("tools", "data", "config")

#: The routers RM-18 made thin. `_payperiods` is the HTTP edge of payroll loading.
THIN_ROUTERS = ("claims", "findings", "scope", "ingestion", "onezero", "auth", "_payperiods")

#: Routes in a thin router that legitimately do not send a request, and why.
NO_MEDIATOR = {
    ("claims", "lifecycle"): "the status and outcome vocabulary, read from the domain enums; no data is read",
    ("auth", "me"): "reports the principal the request guard already authenticated",
}

#: Functions under `api/` still longer than the standard. A ratchet: an entry whose
#: function has since been shortened must be removed (`test_the_long_function_list_is_current`).
LONG_FUNCTIONS: dict[str, str] = {
    "api/chat/dispatch.py::_dispatch": "chat pipelines, tracked in CODE-STANDARDS.md",
    "api/chat/pipelines_core.py::_pipeline_eligibility": "chat pipelines, tracked in CODE-STANDARDS.md",
    "api/chat/pipelines_core.py::_pipeline_portfolio": "chat pipelines, tracked in CODE-STANDARDS.md",
    "api/chat/pipelines_whatif.py::_pipeline_simulate": "chat pipelines, tracked in CODE-STANDARDS.md",
    "api/eligibility.py::eligibility": "one line over; not a RM-18 router",
    "api/forecast.py::forecast": "forecast routes, not yet moved behind queries",
    "api/forecast.py::monthly_alerts": "forecast routes, not yet moved behind queries",
    "api/forecast.py::performance_dashboard": "forecast routes, not yet moved behind queries",
    "api/retroactive.py::one_zero_retroactive_scan": "retroactive scan, not yet moved behind a query",
    "api/rules.py::rules": "rules catalogue, not yet moved behind a query",
    "api/simulate.py::run_onezero_simulation": "simulator route, not yet moved behind a query",
    "api/summary.py::_stream": "summary stream, tracked separately",
    "api/summary.py::build_brief": "summary brief, tracked separately",
    "api/trend.py::_with_lever": "Gold-read helpers, RM-19 (GoldReader port) moves them",
    "api/trend.py::v2_client_unit_detail": "Gold-read route, RM-19 (GoldReader port) moves it",
    "api/trend.py::v2_client_units": "Gold-read route, RM-19 (GoldReader port) moves it",
    "api/trend.py::v2_employee_detail": "Gold-read route, RM-19 (GoldReader port) moves it",
}

#: What the routers that are NOT thin may still import from the statutory packages.
#: A ratchet: it may not grow, and an import that has gone must leave this list.
STATUTORY_IMPORT_ALLOWANCE: dict[str, frozenset[str]] = {
    "api/forecast.py": frozenset({"config", "tools.credit_math", "tools.forecast", "tools.triggers"}),
    "api/retroactive.py": frozenset({"config", "data.claims", "tools.baseyear", "tools.credit_math"}),
    "api/rules.py": frozenset({"data.claims"}),
    "api/rules_ingestion.py": frozenset({"tools", "tools.rules_ingestion"}),
    "api/simulate.py": frozenset({"tools.credit_math", "tools.simulation"}),
    "api/summary.py": frozenset({"tools", "tools.page_brief"}),
    "api/trend.py": frozenset({"data.sites", "tools.credit_math", "tools.grid_filter"}),
    "api/workspace.py": frozenset({"tools.reference_workspace"}),
}


def _relative(path: Path) -> str:
    return path.relative_to(BACKEND).as_posix()


def _api_files() -> list[Path]:
    return [p for p in sorted(API.rglob("*.py")) if "__pycache__" not in p.parts]


def imported_modules(source: str) -> set[str]:
    """Every absolute module a source imports, lazy imports included."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
            found.update(f"{node.module}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
    return found


def _top(module: str) -> str:
    return module.split(".")[0]


def outward_imports(source: str) -> set[str]:
    return {m for m in imported_modules(source) if _top(m) in _OUTWARD}


def api_imports(source: str) -> set[str]:
    """Imports of the `api` package in any form: `import api`, `from api.x import y`, `from api import x`."""
    return {m for m in imported_modules(source) if _top(m) == "api"}


def long_functions(path: str, source: str) -> set[str]:
    return {
        f.key.split("|", 1)[1]
        for f in measure(path, source)
        if f.key.startswith("function-lines|")
    }


def statutory_imports(source: str) -> set[str]:
    """The modules a source imports from `tools`, `data` or `config` (the package itself for `from tools import x`)."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
        elif isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
    return {m for m in found if _top(m) in _STATUTORY}


def route_functions(source: str) -> dict[str, ast.FunctionDef]:
    """The functions decorated as routes (`@router.get(...)`, `@v2_router.post(...)`)."""
    routes = {}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                call = dec.func if isinstance(dec, ast.Call) else dec
                if isinstance(call, ast.Attribute) and call.attr in {"get", "post", "put", "delete", "patch"}:
                    routes[node.name] = node
    return routes


def calls_the_mediator(node: ast.FunctionDef) -> bool:
    return any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "get_mediator"
        for n in ast.walk(node)
    )


# --- no adapter, no composition root ------------------------------------------------


@pytest.mark.parametrize("path", _api_files(), ids=_relative)
def test_a_router_imports_no_infrastructure_or_bootstrap(path):
    allowed = ROUTER_IMPORT_ALLOWANCE.get(_relative(path), {})
    offending = sorted(m for m in outward_imports(path.read_text(encoding="utf-8")) if _top(m) not in allowed)
    assert not offending, (
        f"{_relative(path)} imports {offending}. A router asks for a collaborator through "
        f"`application.services` (the composition root binds it) or sends a query or command; "
        f"naming an adapter here puts the layer that implements the ports under the one that presents them."
    )


def test_the_router_import_allowance_is_empty_or_justified():
    assert all(reason.strip() for allowed in ROUTER_IMPORT_ALLOWANCE.values() for reason in allowed.values())


@pytest.mark.parametrize("package", ["application", "domain", "infrastructure", "tools", "bootstrap", "channel"])
def test_nothing_outside_the_routers_imports_the_router_package(package):
    violations = []
    for path in sorted((BACKEND / package).rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        if hit := api_imports(path.read_text(encoding="utf-8")):
            violations.append(f"{_relative(path)} -> {sorted(hit)}")
    assert not violations, (
        "an inner ring imports `api`:\n  " + "\n  ".join(violations)
        + "\n\nA use case that needs a router is not a use case; the thing it needs belongs in `application`."
    )


def test_the_assessment_service_is_not_filed_under_the_routers():
    assert not (API / "_assess.py").exists()
    assert (BACKEND / "application" / "assessment.py").exists()


# --- routers are short --------------------------------------------------------------


def _all_long_functions() -> set[str]:
    found: set[str] = set()
    for p in _api_files():
        found |= long_functions(_relative(p), p.read_text(encoding="utf-8"))
    return found


def test_no_router_function_is_longer_than_the_standard_except_the_pinned_ones():
    found = _all_long_functions()
    new = sorted(found - set(LONG_FUNCTIONS))
    assert not new, (
        f"functions under api/ over {LIMITS['function-lines']} lines: {new}. A route parses, dispatches and "
        f"shapes the response; the work belongs in a handler under application/."
    )


def test_the_long_function_list_is_current():
    found = _all_long_functions()
    stale = sorted(set(LONG_FUNCTIONS) - found)
    assert not stale, f"these are within the standard now; remove them from LONG_FUNCTIONS: {stale}"
    assert all(reason.strip() for reason in LONG_FUNCTIONS.values())


# --- the thin routers ---------------------------------------------------------------


@pytest.mark.parametrize("name", THIN_ROUTERS)
def test_a_thin_router_imports_no_statutory_math(name):
    source = (API / f"{name}.py").read_text(encoding="utf-8")
    offending = sorted(statutory_imports(source))
    assert not offending, (
        f"api/{name}.py imports {offending}. The arrangement of engine figures is a handler's job "
        f"(`application/queries/`); a router that imports the engine can compute beside it."
    )


@pytest.mark.parametrize("name", THIN_ROUTERS)
def test_every_route_in_a_thin_router_reaches_the_mediator(name):
    source = (API / f"{name}.py").read_text(encoding="utf-8")
    missing = [
        fn for fn, node in route_functions(source).items()
        if not calls_the_mediator(node) and (name, fn) not in NO_MEDIATOR
    ]
    assert not missing, f"api/{name}.py routes that never call get_mediator(): {missing}"


def test_the_no_mediator_routes_still_exist_and_have_a_reason():
    for (name, fn), reason in NO_MEDIATOR.items():
        assert fn in route_functions((API / f"{name}.py").read_text(encoding="utf-8")), (name, fn)
        assert reason.strip()


def test_the_other_routers_do_not_widen_what_they_import_from_the_statutory_packages():
    widened, stale = [], []
    for path in _api_files():
        rel = _relative(path)
        if path.stem in THIN_ROUTERS:
            continue
        found = frozenset(statutory_imports(path.read_text(encoding="utf-8")))
        allowed = STATUTORY_IMPORT_ALLOWANCE.get(rel, frozenset())
        widened += [f"{rel} -> {m}" for m in sorted(found - allowed)]
        stale += [f"{rel} -> {m}" for m in sorted(allowed - found)]
    assert not widened, f"new statutory imports in a router: {widened}. Put the work behind a query."
    assert not stale, f"these imports are gone; remove them from STATUTORY_IMPORT_ALLOWANCE: {stale}"


# --- the rules bite -----------------------------------------------------------------


def test_the_outward_import_rule_catches_a_lazy_adapter_import():
    source = textwrap.dedent(
        """
        def route():
            from infrastructure.persistence.sqlite_claims import SqliteClaimRepository
            from bootstrap.wiring import get_mediator
        """
    )
    assert {_top(m) for m in outward_imports(source)} == {"infrastructure", "bootstrap"}


def test_the_api_import_rule_catches_every_import_form():
    for line in ("import api.claims", "from api.claims import router", "from api import claims"):
        assert api_imports(line + "\n"), line
    assert not api_imports("from application import api_client\nimport apiary\n")


def test_the_length_rule_catches_a_long_route():
    source = "def route():\n" + "    x = 1\n" * 45
    assert long_functions("api/x.py", source) == {"api/x.py::route"}


def test_the_statutory_rule_catches_the_engine_and_the_config():
    source = "from tools.credit_math import load_pack_one_zero\nimport config\nfrom data.sites import worksite_name\n"
    assert {_top(m) for m in statutory_imports(source)} == {"tools", "config", "data"}


def test_the_route_rule_tells_a_route_that_sends_from_one_that_does_not():
    source = textwrap.dedent(
        """
        @router.get("/a")
        def sends():
            return get_mediator().send(Q())

        @router.get("/b")
        def computes():
            return {"x": 1}
        """
    )
    routes = route_functions(source)
    assert calls_the_mediator(routes["sends"]) and not calls_the_mediator(routes["computes"])
