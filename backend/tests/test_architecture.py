"""The layering is enforced here, not merely described in an ADR.

An architecture document says what should be true. This says what *is* true, and
fails when it stops being true. Without it, the first import that points the
wrong way is invisible until someone reads the file, and by then several more
have followed it.

Three rules, in order of how much damage breaking them does:

1. **The domain calculation is pure.** No file reads, no network, no database,
   no environment. This is what makes a run replayable years later when a return
   is examined — the same inputs and rules produce the same bytes, because there
   is nothing else for them to depend on.

2. **Dependencies point inward.** Presentation may know about the domain; the
   domain may not know about presentation. A domain that imports a web framework
   cannot be tested, reused, or moved into a data pipeline — and moving the
   calculation into a Fabric pipeline is on the roadmap.

3. **One definition of a statutory quantity.** Average Headcount decides the
   credit. Two implementations is two answers, and we have already shipped that
   bug once: Position said a client-year was worth $0 while Plan said $252,280.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent

# Modules whose absence of I/O is the point. `credit_math` is deliberately NOT
# here: it still loads rule packs from disk. Extracting that is planned, and
# listing it before the extraction would make this test a lie.
PURE_DOMAIN = [
    "domain/calculation/onezero.py",
    "domain/calculation/headcount.py",
    "domain/calculation/proximity.py",
]

FORBIDDEN_IN_PURE_DOMAIN = {
    "sqlite3", "requests", "httpx", "urllib", "socket",
    "fastapi", "starlette", "uvicorn", "pydantic",
    "deltalake", "azure", "boto3",
}

# `os` and `pathlib` are not inherently impure — a module may import Path for a
# type hint — so those are checked by call site below rather than by import.
IMPURE_CALLS = {"open", "getenv", "environ"}


def _imports(path: Path) -> set[str]:
    """Top-level package name of every import in a module."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


def _relative_imports(path: Path) -> set[str]:
    """Modules imported relatively, resolved to their package."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module and node.level > 0
    }


def _python_files(package: str) -> list[Path]:
    root = BACKEND / package
    if not root.is_dir():
        return []
    return [
        p for p in root.rglob("*.py")
        if "__pycache__" not in p.parts and p.name != "__init__.py"
    ]


# --- 1. The domain calculation is pure -------------------------------------


@pytest.mark.parametrize("relative", PURE_DOMAIN)
def test_pure_domain_modules_do_no_io(relative):
    path = BACKEND / relative
    assert path.exists(), f"{relative} has moved; update this test deliberately"

    offending = _imports(path) & FORBIDDEN_IN_PURE_DOMAIN
    assert not offending, (
        f"{relative} imports {sorted(offending)}. The calculation must stay "
        f"deterministic — a run has to replay identically years later. Move the "
        f"I/O to infrastructure/ and pass the result in."
    )


@pytest.mark.parametrize("relative", PURE_DOMAIN)
def test_pure_domain_modules_do_not_read_files_or_environment(relative):
    tree = ast.parse((BACKEND / relative).read_text(encoding="utf-8"))
    calls = {
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Name, ast.Attribute))
    }
    offending = calls & IMPURE_CALLS
    assert not offending, (
        f"{relative} calls {sorted(offending)}. Reading a file or an environment "
        f"variable makes the result depend on the machine it ran on, which is "
        f"exactly what a filed figure cannot do."
    )


# --- 2. Dependencies point inward ------------------------------------------


def test_domain_does_not_import_presentation_or_infrastructure():
    """The innermost layer knows nothing about the ones around it."""
    violations = []
    for path in _python_files("domain"):
        bad = (_imports(path) | _relative_imports(path)) & {"api", "infrastructure", "main"}
        if bad:
            violations.append(f"{path.relative_to(BACKEND).as_posix()} -> {sorted(bad)}")
    assert not violations, (
        "domain/ imports outward:\n  " + "\n  ".join(violations)
        + "\n\nThe domain must be usable without a web server or a database. "
        "Moving the calculation into a data pipeline depends on this holding."
    )


def test_tools_do_not_import_routers():
    """Compute is called BY presentation, never the other way round."""
    violations = []
    for path in _python_files("tools"):
        if "api" in _imports(path):
            violations.append(path.relative_to(BACKEND).as_posix())
    assert not violations, (
        "tools/ imports from api/:\n  " + "\n  ".join(violations)
        + "\n\nThis makes the calculation depend on HTTP routing, and creates "
        "import cycles that only appear under some entry points."
    )


def test_infrastructure_does_not_import_routers():
    """Adapters implement domain ports; they do not know who calls them."""
    violations = []
    for path in _python_files("infrastructure"):
        if "api" in _imports(path):
            violations.append(path.relative_to(BACKEND).as_posix())
    assert not violations, "infrastructure/ imports from api/:\n  " + "\n  ".join(violations)


def test_domain_does_not_import_tools():
    """`tools/` is the service ring around the domain, not part of it.

    `StatutoryFloors` used to live in `tools/credit_math.py`, so the pure
    proximity calculation had to reach outward into `tools/` just to type its
    own arguments. The value object now lives in `domain/calculation/floors.py`
    and `tools/` re-exports it. Nothing in the domain may reach back out.
    """
    violations = []
    for path in _python_files("domain"):
        if "tools" in (_imports(path) | _relative_imports(path)):
            violations.append(path.relative_to(BACKEND).as_posix())
    assert not violations, (
        "domain/ imports from tools/:\n  " + "\n  ".join(violations)
        + "\n\nIf the domain needs a type, the type belongs in the domain. If "
        "it needs I/O, the caller does the I/O and passes the result in."
    )


#: The one place `application/` may still name something under `api/`.
#: `api/_assess.py` holds no routing — it is an application service that was
#: filed under the router package, and it depends on `api/_payperiods.py`,
#: which is a payroll reader that raises `HTTPException`. Relocating both is a
#: real refactor that touches every router, tracked separately. The allowance
#: is explicit so it stays one exception and does not become a pattern.
_APPLICATION_IMPORT_ALLOWANCE = {"api._assess"}


def test_application_does_not_import_a_router():
    """Use cases must not reach into presentation to find their dependencies.

    Every handler used to do `from api.claims import get_repository` — the
    composition root lived in a router, so driving a use case from anything but
    HTTP dragged FastAPI in with it. Composition now lives in
    `application/wiring.py`, which is where [ADR-003] says it belongs.
    """
    violations = []
    for path in _python_files("application"):
        source = path.read_text(encoding="utf-8")
        for line in source.splitlines():
            stripped = line.strip()
            if not stripped.startswith("from api."):
                continue
            module = stripped.split()[1]
            if module in _APPLICATION_IMPORT_ALLOWANCE:
                continue
            violations.append(f"{path.relative_to(BACKEND).as_posix()} -> {module}")
    assert not violations, (
        "application/ imports from api/:\n  " + "\n  ".join(violations)
        + "\n\nPut the dependency in application/wiring.py and import it from "
        "there. A use case that needs a router is not a use case."
    )


def test_application_layer_does_not_import_a_web_framework():
    """Use cases must be drivable by something other than HTTP.

    The calculation is expected to move into a Fabric pipeline. A handler that
    raises `HTTPException` cannot be called from a notebook or a scheduled job
    without dragging FastAPI in, so handlers raise domain exceptions and the
    router maps them onto status codes.
    """
    violations = []
    for path in _python_files("application"):
        bad = _imports(path) & {"fastapi", "starlette"}
        if bad:
            violations.append(f"{path.relative_to(BACKEND).as_posix()} -> {sorted(bad)}")
    assert not violations, (
        "application/ imports a web framework:\n  " + "\n  ".join(violations)
        + "\n\nRaise a domain exception instead and let the router choose the "
        "status code."
    )


def test_every_request_type_is_a_command_or_a_query():
    """The read/write split is the reason the mediator exists.

    A request that is neither has escaped it, and the write path can then
    quietly acquire a read's casualness about attribution.
    """
    from application.mediator import Command, Query

    offending = []
    for package in ("application/commands", "application/queries"):
        for path in _python_files(package.split("/")[0]):
            if package.split("/")[1] not in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                bases = {b.id for b in node.bases if isinstance(b, ast.Name)}
                looks_like_request = node.name.endswith(("Command", "Query"))
                if looks_like_request and not (bases & {"Command", "Query"}):
                    offending.append(
                        f"{path.relative_to(BACKEND).as_posix()}:{node.lineno} "
                        f"{node.name}"
                    )
    assert not offending, (
        "request types not deriving from Command or Query:\n  "
        + "\n  ".join(offending)
    )


def test_no_module_relies_on_a_name_it_never_imported():
    """Catches the extraction bug: code moved out, its imports left behind.

    Splitting `onezero.py` produced three modules that referenced
    `defaultdict`, `apply_pay_code_policy` and `preprocess` without importing
    them. Python raises only when the line executes, so the failure surfaced as
    five unrelated endpoint tests rather than as an obvious import error.

    Deliberately narrow: module-level names that are called or subscripted, not
    every local. A broad version produces false positives and gets muted.
    """
    import builtins

    known_builtins = set(dir(builtins)) | {
        "list", "dict", "set", "tuple", "str", "int", "float", "bool",
        "Any", "Optional", "Iterable", "Iterator", "Callable", "Sequence",
        "__name__", "__file__", "__doc__", "self", "cls",
    }

    violations = []
    for package in ("domain", "application", "infrastructure", "api", "tools"):
        for path in _python_files(package):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

            bound = set(known_builtins)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    bound |= {a.asname or a.name.split(".")[0] for a in node.names}
                elif isinstance(node, ast.ImportFrom):
                    bound |= {a.asname or a.name for a in node.names}
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    bound.add(node.name)
                    bound |= {a.arg for a in getattr(node, "args", ast.arguments(
                        posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]
                    )).args}
                elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                    bound.add(node.id)
                elif isinstance(node, ast.arg):
                    bound.add(node.arg)
                elif isinstance(node, (ast.comprehension,)):
                    for n in ast.walk(node.target):
                        if isinstance(n, ast.Name):
                            bound.add(n.id)
                elif isinstance(node, ast.ExceptHandler) and node.name:
                    bound.add(node.name)
                elif isinstance(node, (ast.Global, ast.Nonlocal)):
                    bound |= set(node.names)

            # Four shapes, each of which has actually slipped through a refactor:
            #   f(...)              call              -- defaultdict()
            #   CONST["k"]          subscript         -- _BUILD_IN_HOUSE_BENCHMARK
            #   mod.attr(...)       attribute call    -- date.today()
            #   mod.attr            attribute read    -- timezone.utc
            # Bare `Name` references stay excluded: those are usually locals this
            # cheap scope model did not track, and a test with false positives
            # gets muted, which is worse than not having the test.
            for node in ast.walk(tree):
                name = None
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        name = node.func.id
                    elif isinstance(node.func, ast.Attribute) and isinstance(
                        node.func.value, ast.Name
                    ):
                        name = node.func.value.id
                elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
                    name = node.value.id
                elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                    name = node.value.id

                if name and name not in bound:
                    violations.append(
                        f"{path.relative_to(BACKEND).as_posix()}:{node.lineno} "
                        f"uses undefined {name!r}"
                    )

            # Type annotations, which matter more here than in ordinary Python.
            # FastAPI reads them at import time to decide what a parameter IS:
            # an unresolved `request: Request` becomes a required QUERY
            # parameter rather than the injected object, so every call to that
            # endpoint returns 422 and nothing raises. A router split produced
            # exactly that, and seven alert tests failed for a reason that
            # looked nothing like a missing import.
            for node in ast.walk(tree):
                annotations = []
                if isinstance(node, ast.arg) and node.annotation is not None:
                    annotations.append(node.annotation)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.returns is not None:
                        annotations.append(node.returns)
                elif isinstance(node, ast.AnnAssign) and node.annotation is not None:
                    annotations.append(node.annotation)

                for annotation in annotations:
                    for part in ast.walk(annotation):
                        if isinstance(part, ast.Name) and part.id not in bound:
                            violations.append(
                                f"{path.relative_to(BACKEND).as_posix()}:{part.lineno} "
                                f"annotates with undefined {part.id!r}"
                            )

    assert not violations, (
        "names used but never imported or defined:\n  " + "\n  ".join(sorted(set(violations)))
    )


def test_commands_live_in_commands_and_queries_in_queries():
    """A write filed under queries is a write nobody will look for."""
    misplaced = []
    for path in _python_files("application"):
        if "commands" not in path.parts and "queries" not in path.parts:
            continue
        expected = "Command" if "commands" in path.parts else "Query"
        wrong = "Query" if expected == "Command" else "Command"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name.endswith(wrong):
                bases = {b.id for b in node.bases if isinstance(b, ast.Name)}
                if wrong in bases:
                    misplaced.append(
                        f"{path.relative_to(BACKEND).as_posix()}:{node.lineno} "
                        f"{node.name}"
                    )
    assert not misplaced, "requests in the wrong package:\n  " + "\n  ".join(misplaced)


# --- 3. One definition of a statutory quantity -----------------------------


def test_average_headcount_has_exactly_one_implementation():
    """The $0-versus-$252,280 bug, pinned so it cannot come back.

    Position and Plan each had their own row selection and their own analysis
    window, and disagreed about what the same client-year was worth. Re-exports
    are fine — a second `def` is not.
    """
    definitions = []
    for path in BACKEND.rglob("*.py"):
        if any(p in path.parts for p in ("__pycache__", ".venv", "tests")):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "average_headcount":
                body = [n for n in node.body if not isinstance(n, ast.Expr)]
                # A one-line delegating wrapper is a re-export, not a rival.
                if not (len(body) == 1 and isinstance(body[0], ast.Return)):
                    definitions.append(
                        f"{path.relative_to(BACKEND).as_posix()}:{node.lineno}"
                    )
    assert len(definitions) == 1, (
        f"average_headcount is implemented {len(definitions)} times: {definitions}. "
        f"It decides the credit; a second implementation is a second answer. "
        f"Delegate to domain/calculation/headcount.py instead."
    )


def test_row_state_has_exactly_one_implementation():
    """Which state a row belongs to decides which statute applies."""
    definitions = []
    for path in BACKEND.rglob("*.py"):
        if any(p in path.parts for p in ("__pycache__", ".venv", "tests")):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "row_state":
                body = [n for n in node.body if not isinstance(n, ast.Expr)]
                if not (len(body) == 1 and isinstance(body[0], ast.Return)):
                    definitions.append(
                        f"{path.relative_to(BACKEND).as_posix()}:{node.lineno}"
                    )
    assert len(definitions) == 1, (
        f"row_state is implemented {len(definitions)} times: {definitions}. "
        f"Two readings means a row can be visible to one caller and invisible "
        f"to another, which renders as an empty screen rather than an error."
    )


# --- Configuration is not documentation ------------------------------------


def test_runtime_does_not_load_configuration_from_docs():
    """A docs reorganisation must not be able to stop the engine booting.

    Methodology sets were read from `docs/data/` until exactly that happened.
    They are configuration — versioned alongside the rule packs they pair with —
    and they now live in `backend/rules/methodology/`.
    """
    violations = []
    for package in ("tools", "api", "domain", "infrastructure", "data"):
        for path in _python_files(package):
            text = path.read_text(encoding="utf-8")
            if '"docs"' in text or "'docs'" in text:
                violations.append(path.relative_to(BACKEND).as_posix())
    assert not violations, (
        "runtime code references the docs/ tree:\n  " + "\n  ".join(violations)
        + "\n\nDocumentation is reorganised freely; configuration is not. Put "
        "the file under backend/rules/ and reference it there."
    )


# --- Keyless by default ----------------------------------------------------


def test_no_secret_is_injected_into_the_deployed_apps():
    """Every Azure dependency authenticates with a managed identity.

    Storage has shared keys off, Foundry has `disableLocalAuth`, and App
    Insights accepts only Entra-authenticated ingestion. That is why there is no
    Key Vault by default: a vault with nothing in it is ceremony.

    This fails if someone reintroduces a key in the Terraform - which is the
    moment to ask whether the dependency supports Entra before reaching for a
    vault.
    """
    terraform = "\n".join(
        p.read_text(encoding="utf-8") for p in (BACKEND.parent / "infra").rglob("*.tf")
        if ".terraform" not in p.parts
    )

    secret_shaped = (
        "primary_access_key", "secondary_access_key", "primary_connection_string",
        "listKeys", "instrumentation_key", "client_secret =", "sas_url",
    )
    found = [token for token in secret_shaped if token in terraform]
    assert not found, f"the Terraform reads a key: {found}. Prefer Entra and a role assignment."

    import re

    for pattern, resource in [
        (r"shared_access_key_enabled\s*=\s*false", "Storage"),
        (r"disableLocalAuth\s*=\s*true", "Foundry"),
        (r"local_authentication_enabled\s*=\s*false", "Application Insights"),
    ]:
        assert re.search(pattern, terraform), f"{resource} no longer disables key auth ({pattern})"


def test_telemetry_authenticates_with_the_managed_identity():
    """The App Insights connection string carries an InstrumentationKey, and on
    its own that key lets anyone holding it write to our workspace. Passing a
    credential makes Entra the thing that authorises ingestion."""
    source = (BACKEND / "telemetry.py").read_text(encoding="utf-8")
    assert "credential=" in source, (
        "configure_azure_monitor is being called without a credential, so "
        "telemetry ingestion is authenticated by the InstrumentationKey alone."
    )
    assert "DefaultAzureCredential" in source


# --- Tenant isolation: Warehouse SQL goes through tenant_sql [DATA-4] --------
#
# The Warehouse has no partition key. One forgotten `client_id` predicate
# returns every client's rows, and the screen shows them under the wrong name.
# `infrastructure/persistence/tenant_sql.py` binds the predicate itself; this
# rule makes it the only way a Warehouse adapter can execute anything.

_PERSISTENCE = BACKEND / "infrastructure" / "persistence"
_HELPER_FACTORIES = {"TenantScopedQuery", "tenant_exempt"}
_EXECUTE_METHODS = {"execute", "executemany"}


def _tenant_scoped_modules() -> list[Path]:
    return sorted(_PERSISTENCE.glob("warehouse_*.py")) + [_PERSISTENCE / "fabric_warehouse.py"]


def _callee(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
    return None


def direct_executions(source: str) -> list[str]:
    """Every `.execute(` / `.executemany(` whose receiver is not a tenant helper.

    A receiver counts as a helper when it is a call to `TenantScopedQuery`,
    `tenant_exempt`, or a function annotated to return `TenantScopedQuery`, or
    a name/attribute assigned from one of those.
    """
    tree = ast.parse(source)
    factories = set(_HELPER_FACTORIES)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is not None:
            if ast.unparse(node.returns).split(".")[-1] in {"TenantScopedQuery", "TenantExemptQuery"}:
                factories.add(node.name)
    helpers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _callee(node.value) in factories:
            helpers.update(ast.unparse(t) for t in node.targets)
        elif isinstance(node, ast.AnnAssign) and node.value is not None and _callee(node.value) in factories:
            helpers.add(ast.unparse(node.target))
    found: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr not in _EXECUTE_METHODS:
            continue
        receiver = node.func.value
        if _callee(receiver) in factories or ast.unparse(receiver) in helpers:
            continue
        found.append(f"line {node.lineno}: {ast.unparse(node)[:90]}")
    return found


@pytest.mark.parametrize("path", _tenant_scoped_modules(), ids=lambda p: p.name)
def test_warehouse_adapters_execute_sql_only_through_the_tenant_helper(path):
    assert path.exists()
    violations = direct_executions(path.read_text(encoding="utf-8"))
    assert not violations, (
        f"{path.name} executes SQL directly:\n  " + "\n  ".join(violations)
        + "\n\nRoute it through infrastructure/persistence/tenant_sql.py: "
        "TenantScopedQuery(client_id) for one client's rows, or "
        "tenant_exempt(reason) where spanning clients is the point."
    )


def test_the_tenant_rule_covers_the_new_adapters():
    names = {p.name for p in _tenant_scoped_modules()}
    assert {"warehouse_claims.py", "warehouse_findings.py", "warehouse_gold.py", "fabric_warehouse.py"} <= names


def test_the_tenant_rule_catches_a_crafted_violation():
    """Mutation check: the rule must FAIL on code that bypasses the helper."""
    crafted = (
        "def read(conn, client_id):\n"
        "    cursor = conn.cursor()\n"
        "    cursor.execute('SELECT * FROM tcc_ops.program_claim')\n"
        "    conn.execute('DELETE FROM tcc_ops.program_claim')\n"
        "    cursor.executemany('INSERT INTO t VALUES (?)', [[1]])\n"
    )
    assert len(direct_executions(crafted)) == 3

    compliant = (
        "def read(conn, client_id):\n"
        "    scoped = TenantScopedQuery(client_id)\n"
        "    scoped.execute(conn.cursor(), 'SELECT * FROM t WHERE {tenant}')\n"
        "    TenantScopedQuery(client_id).execute(conn.cursor(), 'SELECT 1 FROM t WHERE {tenant}')\n"
        "    tenant_exempt('reason').execute(conn.cursor(), 'SELECT 1')\n"
    )
    assert direct_executions(compliant) == []


@pytest.mark.parametrize(
    "module, original, mutated",
    [
        ("warehouse_claims.py", "TenantScopedQuery(client_id).execute(cursor, sql, list(params))",
         "cursor.execute(sql, list(params))"),
        ("warehouse_findings.py", "TenantScopedQuery(client_id).execute(cursor, sql, params)",
         "cursor.execute(sql, params)"),
        ("fabric_warehouse.py", '_KEEPALIVE.execute(cursor, "SELECT 1")', 'cursor.execute("SELECT 1")'),
    ],
)
def test_the_tenant_rule_catches_a_mutated_real_adapter(module, original, mutated):
    """Mutation check on the shipped code: undo one helper call and the rule fires."""
    source = (_PERSISTENCE / module).read_text(encoding="utf-8")
    assert original in source, f"{module} changed; update this mutation"
    assert direct_executions(source) == []
    assert direct_executions(source.replace(original, mutated, 1)), f"mutating {module} went undetected"
