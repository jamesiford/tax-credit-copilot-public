"""What the gateway may import, log and serve. [CH-06, ADR-003]

The gateway is the only new public surface, so its boundaries are rules that fail the
build rather than conventions. It routes to the API and holds no business rule: no
router, no agent, no persistence adapter of its own, and nothing from `application/`
beyond the catalog, the envelope types, the audit port and the numeric guard. It never
logs a token. And it serves exactly the routes in `channel_route_inventory.json`.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
CHANNEL = BACKEND / "channel"
INVENTORY = BACKEND / "tests" / "channel_route_inventory.json"

#: The `application` modules the gateway may use, each for a stated reason.
ALLOWED_APPLICATION = frozenset({
    "application.acting_user",                 # the header the API parses
    "application.agent_audit",                 # the narrator-agent audit row (standard library + domain only)
    "application.capabilities.catalog",        # the tool contract
    "application.capabilities.envelope",       # the result shape
    "application.capabilities.verify",         # verify_figures, over the ledger
    "application.capabilities.catalog_types",  # via catalog
    "application.channel_audit",               # the auditor and its port
    "application.channel_wiring",              # the audit trail and writer entitlement, without the engine
    "application.composer_render",             # the platform's own block renderer
    "application.deployment",                  # is_deployed, store_choice
    "application.display_names",               # the display-name port and the placeholder rule (standard library only)
    "application.identity",                    # ActingUser
    "application.rate_limit",                  # the per-user token bucket (standard library only), shared with the API's data-query budget [CH-16c]
})
FORBIDDEN_PREFIXES = ("api.", "agents.", "tools.", "infrastructure.persistence", "application.wiring",
                      "application.queries", "application.commands", "application.mediator", "domain.calculation")
LOG_METHODS = {"debug", "info", "warning", "error", "exception", "critical", "log"}
SECRET_WORDS = re.compile(r"token|authorization|bearer|password|secret", re.IGNORECASE)


def imports(source: str) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def forbidden_imports(source: str) -> list[str]:
    return sorted(m for m in imports(source) if m.startswith(FORBIDDEN_PREFIXES) or m in {"api", "agents", "tools"})


PACKAGES_IMPORTED_BY_NAME = frozenset({"application", "application.capabilities"})


def application_modules(source: str) -> set[str]:
    """Every `application` module the source imports; `from application import x` means `application.x`."""
    used: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            used.update(a.name for a in node.names if a.name.startswith("application."))
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0 and node.module.startswith("application"):
            if node.module in PACKAGES_IMPORTED_BY_NAME:
                used.update(f"{node.module}.{a.name}" for a in node.names)
            else:
                used.add(node.module)
    return used


def unlisted_application_imports(source: str) -> list[str]:
    """`application.*` modules the gateway has no stated reason to use."""
    return sorted(application_modules(source) - ALLOWED_APPLICATION)


def logged_secrets(source: str) -> list[int]:
    """Line numbers of logging calls that mention a token, authorization header or secret."""
    bad: list[int] = []
    for node in ast.walk(ast.parse(source)):
        is_log = (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in LOG_METHODS
                  and isinstance(node.func.value, ast.Name) and node.func.value.id in {"log", "logger", "logging"})
        if is_log and any(SECRET_WORDS.search(ast.unparse(arg)) for arg in node.args):
            bad.append(node.lineno)
    return bad


def channel_sources() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(CHANNEL.glob("*.py"))}


@pytest.mark.parametrize("name", sorted(channel_sources()))
def test_the_gateway_imports_no_router_agent_adapter_or_engine(name):
    assert forbidden_imports(channel_sources()[name]) == []


@pytest.mark.parametrize("name", sorted(channel_sources()))
def test_the_gateway_uses_only_the_application_modules_on_the_list(name):
    assert unlisted_application_imports(channel_sources()[name]) == []


@pytest.mark.parametrize("name", sorted(channel_sources()))
def test_the_gateway_never_logs_a_token(name):
    assert logged_secrets(channel_sources()[name]) == []


def test_importing_the_gateway_does_not_load_the_engine():
    import subprocess
    import sys

    code = (
        "import sys, channel.app\n"
        "heavy = [m for m in sys.modules if m.startswith(('application.queries', 'application.commands', "
        "'application.wiring', 'application.mediator', 'api.', 'agents', 'tools.', 'infrastructure.persistence'))]\n"
        "print(','.join(heavy))"
    )
    done = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, check=True)
    assert done.stdout.strip() == ""


def test_the_gateway_serves_exactly_the_pinned_routes(tmp_path):
    from gateway_harness import build_gateway

    routes = sorted(f"{method} {route.path}" for route in build_gateway(tmp_path).client.app.routes
                    for method in sorted(route.methods or ()) if method != "HEAD")
    pinned = json.loads(INVENTORY.read_text(encoding="utf-8"))
    assert routes == sorted(pinned), (
        "the gateway's routes changed. It is the only new public surface: if this is deliberate, "
        "update tests/channel_route_inventory.json in the same commit.")


def test_the_inventory_is_sorted_and_free_of_duplicates():
    pinned = json.loads(INVENTORY.read_text(encoding="utf-8"))
    assert pinned == sorted(set(pinned))


# ----------------------------------------------------------- the rules bite


def test_the_rules_catch_crafted_violations():
    assert forbidden_imports("from api.capabilities import router") == ["api.capabilities", "api.capabilities.router"]
    assert forbidden_imports("import agents.factory") == ["agents.factory"]
    assert forbidden_imports("from infrastructure.persistence.sqlite_channel import X")
    assert forbidden_imports("from application.wiring import get_mediator")
    assert unlisted_application_imports("from application.queries.get_proximity import X") == ["application.queries.get_proximity"]
    assert unlisted_application_imports("from application.capabilities import registry") == ["application.capabilities.registry"]
    assert unlisted_application_imports("from application.channel_audit import AuditCall") == []
    assert logged_secrets("import logging\nlog = logging.getLogger('x')\nlog.info('got %s', token)") == [3]
    assert logged_secrets("log.warning(f'bad {request.headers[\"authorization\"]}')") == [1]
    assert logged_secrets("log.info('caller authorised: kind=%s', caller.kind)") == []
