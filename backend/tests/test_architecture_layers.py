"""The ring rule, enforced: nothing inside points outward, and one package composes. [ADR-003, RM-17]

    presentation (api, channel, main) -> application -> domain
    infrastructure implements the ports the inner two declare
    bootstrap is outside all of them and is the ONLY package that names an adapter

`test_architecture.py` holds the older, narrower rules (a pure calculation, no routers
in `application/`). This file is the rest of the ring, written as one table so a new
exception has to be added to a list with a reason, not slipped into an import.

Every import counts, including one inside a function: the composition root used to hide
its adapters in lazy imports, and a rule that only read the top of the file was the
reason `application/wiring.py` could name forty-seven of them.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent

#: Web frameworks, cloud and agent SDKs, database drivers and HTTP clients. An inner layer that
#: imports one cannot be driven from a notebook or a pipeline, and cannot be tested without it.
SDK_ROOTS = frozenset({
    "fastapi", "starlette", "uvicorn", "azure", "agent_framework", "agent_framework_foundry",
    "agent_framework_openai", "openai", "pyodbc", "httpx", "requests", "aiohttp", "deltalake",
    "boto3", "msal", "sqlalchemy", "sqlite3",
})

#: What `application` may never import: the adapters it declares ports for, the composition root, and
#: the entry points. (`api` has its own rule with its one allowance in `test_architecture.py`.)
APPLICATION_FORBIDDEN = frozenset({"infrastructure", "bootstrap", "channel", "main"})

#: Every ring outside the domain. The domain may import the standard library and itself, nothing else.
OUTWARD = frozenset({
    "application", "infrastructure", "bootstrap", "api", "channel", "tools", "data", "config",
    "agents", "main", "telemetry",
})

#: Third-party packages `application` genuinely needs, each for a stated reason. Anything else that
#: is not the standard library or a sibling layer fails `test_application_uses_no_unlisted_third_party_package`.
APPLICATION_THIRD_PARTY = {
    "jsonschema": "validates a tool call's arguments against its catalog schema",
    "openpyxl": "the claim package is an Excel workbook",
}

def _roots(source: str) -> set[str]:
    """Top-level package of every absolute import in the source, lazy ones included."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


def _files(package: str) -> list[Path]:
    return sorted(p for p in (BACKEND / package).rglob("*.py") if "__pycache__" not in p.parts)


def _violations(package: str, forbidden: frozenset[str]) -> list[str]:
    out = []
    for path in _files(package):
        bad = sorted(_roots(path.read_text(encoding="utf-8")) & forbidden)
        if bad:
            out.append(f"{path.relative_to(BACKEND).as_posix()} -> {bad}")
    return out


def test_application_imports_nothing_from_infrastructure_the_composition_root_or_an_entry_point():
    violations = _violations("application", APPLICATION_FORBIDDEN)
    assert not violations, (
        "application/ imports outward:\n  " + "\n  ".join(violations)
        + "\n\nDeclare a port in application/ (or domain/) and bind the adapter in bootstrap/. "
        "`application.services` is how a handler asks for what the root provides."
    )


def test_the_domain_imports_only_the_standard_library_and_itself():
    import sys

    allowed = set(sys.stdlib_module_names) | {"__future__", "domain"}
    violations = []
    for path in _files("domain"):
        extra = sorted(_roots(path.read_text(encoding="utf-8")) - allowed)
        if extra:
            violations.append(f"{path.relative_to(BACKEND).as_posix()} -> {extra}")
    assert not violations, (
        "domain/ imports outward or from a third party:\n  " + "\n  ".join(violations)
        + "\n\nThe calculation must run in a notebook or a pipeline with nothing installed but Python."
    )


@pytest.mark.parametrize("package", ["application", "domain"])
def test_the_inner_layers_import_no_web_framework_cloud_sdk_or_driver(package):
    violations = _violations(package, SDK_ROOTS)
    assert not violations, (
        f"{package}/ imports an SDK:\n  " + "\n  ".join(violations)
        + "\n\nAn SDK belongs in an adapter under infrastructure/, behind a port."
    )


def test_application_uses_no_unlisted_third_party_package():
    import sys

    known = set(sys.stdlib_module_names) | {"__future__"} | OUTWARD | {"domain"} | set(APPLICATION_THIRD_PARTY)
    violations = []
    for path in _files("application"):
        extra = sorted(_roots(path.read_text(encoding="utf-8")) - known)
        if extra:
            violations.append(f"{path.relative_to(BACKEND).as_posix()} -> {extra}")
    assert not violations, (
        "application/ imports an unlisted third-party package:\n  " + "\n  ".join(violations)
        + "\n\nAdd it to APPLICATION_THIRD_PARTY with the reason, or put it behind a port."
    )


def test_the_adapters_and_the_core_do_not_import_the_composition_root_or_an_entry_point():
    """`bootstrap` is the outermost ring: only an entry point, a script or a test reaches in."""
    forbidden = frozenset({"bootstrap", "channel", "main"})
    violations = []
    for package in ("infrastructure", "domain", "application"):
        violations += _violations(package, forbidden)
    assert not violations, "an inner ring imports the composition root:\n  " + "\n  ".join(violations)


def test_bootstrap_is_the_only_package_that_names_an_adapter_on_behalf_of_the_application():
    """`bootstrap` imports `infrastructure`; nothing in `application` or `domain` does (rules above)."""
    named = {
        path.relative_to(BACKEND).as_posix()
        for path in _files("bootstrap")
        if "infrastructure" in _roots(path.read_text(encoding="utf-8"))
    }
    assert named, "bootstrap/ no longer composes any adapter; the rule above is checking an empty ring"


def test_the_package_init_imports_nothing_so_the_gateway_stays_light():
    assert not _roots((BACKEND / "bootstrap" / "__init__.py").read_text(encoding="utf-8"))


# ---------------------------------------------------- every name the application asks for is answered


def _requested_service_names() -> set[str]:
    names: set[str] = set()
    for module in ("services", "source_ports", "gold_ports"):
        for node in ast.walk(ast.parse((BACKEND / "application" / f"{module}.py").read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "resolve"
                    and node.args and isinstance(node.args[0], ast.Constant)):
                names.add(node.args[0].value)
    return names


def test_the_composition_root_provides_every_service_the_application_asks_for():
    from application import services
    import bootstrap.data_wiring  # noqa: F401 - binds the data-query service
    import bootstrap.wiring  # noqa: F401 - binds everything else

    requested = _requested_service_names()
    assert len(requested) >= 20, "the scan found almost nothing; it is no longer reading `resolve(...)`"
    missing = sorted(requested - set(services._providers))
    assert not missing, f"the application asks for services the composition root never binds: {missing}"


def test_a_getter_replaced_on_the_wiring_module_is_what_a_handler_receives(monkeypatch):
    """The reason a provider is looked up per call: tests, and `set_*`, swap the getter after start-up."""
    from application import services
    from bootstrap import wiring

    sentinel = object()
    monkeypatch.setattr(wiring, "get_gold_reader", lambda: sentinel)
    assert services.get_gold_reader() is sentinel


def test_an_unbound_service_names_the_cause(monkeypatch):
    from application import services

    monkeypatch.setattr(services, "_providers", {})
    with pytest.raises(services.ServiceNotBound, match="composition root"):
        services.get_claim_repository()


# ------------------------------------------------------------------ the rules bite


def test_the_rules_catch_a_crafted_violation(tmp_path):
    lazy = "def f():\n    from infrastructure.persistence.sqlite_claims import SqliteClaimRepository\n"
    assert _roots(lazy) & APPLICATION_FORBIDDEN == {"infrastructure"}, "a lazy import must count"
    assert _roots("import bootstrap.wiring") & APPLICATION_FORBIDDEN == {"bootstrap"}
    assert _roots("from azure.identity import DefaultAzureCredential") & SDK_ROOTS == {"azure"}
    assert _roots("import pyodbc, httpx") & SDK_ROOTS == {"pyodbc", "httpx"}
    assert _roots("from fastapi import HTTPException") & SDK_ROOTS == {"fastapi"}
    assert _roots("from application.ports import X") & OUTWARD == {"application"}
    assert _roots("from domain.calculation import floors") & OUTWARD == set()
    assert _roots("from . import sibling") == set()
