"""Two RM-03 rules that must stay true, enforced rather than described.

1. **A broad `except` in an audit or entitlement path is never silent.** Where the code catches
   `Exception` to keep a failed audit write from breaking an answer, or a failed writer check from
   granting, the handler must either re-raise or raise the alert (`audit_write_failed`,
   `writer_check_failed`). A handler that only logs is how a trail goes quietly missing.
2. **`AUTH_MODE` is read in one place.** Its default (`entra`) and the rule for when `none` is
   allowed live in `application/auth_policy.py`. A second reader would be a second default.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from application import audit_alert, auth_policy

BACKEND = Path(__file__).resolve().parent.parent

#: module path -> (the alert each broad handler must raise or re-raise instead, the functions to check or None for all).
GUARDED_PATHS = {
    "application/channel_audit.py": ("audit_write_failed", None),
    "application/agent_audit.py": ("audit_write_failed", None),
    "channel/narration.py": ("audit_write_failed", None),
    "api/chat/narration.py": ("audit_write_failed", {"_record_agent_action"}),  # its other handler is a model failure
    "infrastructure/auth/writers.py": ("writer_check_failed", None),
}
#: Handlers in channel/pipeline.py that must alert; the others deny or refuse through the auditor's own alert.
PIPELINE_ALERTING = {"_is_writer": "writer_check_failed"}


def _broad_handlers(tree: ast.AST):
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(function):
            if isinstance(node, ast.ExceptHandler) and (
                node.type is None or (isinstance(node.type, ast.Name) and node.type.id in ("Exception", "BaseException"))
            ):
                yield function.name, node


def _calls(node: ast.AST) -> set[str]:
    names = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            target = child.func
            names.add(target.id if isinstance(target, ast.Name) else getattr(target, "attr", ""))
    return names


def _reraises(node: ast.ExceptHandler) -> bool:
    return any(isinstance(child, ast.Raise) for child in ast.walk(node))


def _tree(relative: str) -> ast.AST:
    return ast.parse((BACKEND / relative).read_text(encoding="utf-8"))


@pytest.mark.parametrize("relative", list(GUARDED_PATHS))
def test_a_broad_except_in_an_audit_or_entitlement_path_raises_its_alert_or_reraises(relative):
    alert, only = GUARDED_PATHS[relative]
    handlers = [(f, h) for f, h in _broad_handlers(_tree(relative)) if only is None or f in only]
    assert handlers, f"{relative}: expected a guarded handler; if it moved, move the rule with it"
    silent = [f"{function}:{h.lineno}" for function, h in handlers if alert not in _calls(h) and not _reraises(h)]
    assert not silent, f"{relative}: a broad except neither raises {alert} nor re-raises: {silent}"


def test_the_gateways_entitlement_check_raises_writer_check_failed():
    handlers = [(f, h) for f, h in _broad_handlers(_tree("channel/pipeline.py")) if f in PIPELINE_ALERTING]
    assert handlers, "the gateway's entitlement check is expected to catch and deny"
    for function, handler in handlers:
        assert PIPELINE_ALERTING[function] in _calls(handler)


def test_the_audit_sources_named_at_call_sites_are_the_declared_ones():
    used: set[str] = set()
    for path in BACKEND.rglob("*.py"):
        relative = path.relative_to(BACKEND).as_posix()
        if relative.startswith(("tests/", ".venv", "venv")) or "site-packages" in relative:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) == "audit_write_failed"
                    and node.args and isinstance(node.args[0], ast.Constant)):
                used.add(node.args[0].value)
    assert used <= set(audit_alert.SOURCES), f"undeclared audit sources: {used - set(audit_alert.SOURCES)}"
    assert used == set(audit_alert.SOURCES), "a declared audit source that nothing raises is an alert that cannot fire"


def test_the_alert_names_are_the_ones_a_log_alert_keys_on():
    assert audit_alert.EVENT == "audit_write_failed" and audit_alert.LOGGER_NAME == "tcc.audit_alert"


# --------------------------------------------------------------------- AUTH_MODE

#: The only modules that name the variable: the policy that owns it, and the gateway, which refuses `none` outright.
AUTH_MODE_READERS = {"application/auth_policy.py", "channel/config.py"}


def test_auth_mode_is_read_in_one_place():
    offenders = []
    for path in BACKEND.rglob("*.py"):
        relative = path.relative_to(BACKEND).as_posix()
        if relative.startswith(("tests/", ".venv", "venv")) or "site-packages" in relative:
            continue
        if re.search(r"""["']AUTH_MODE["']""", path.read_text(encoding="utf-8")) and relative not in AUTH_MODE_READERS:
            offenders.append(relative)
    assert not offenders, f"AUTH_MODE is read outside application/auth_policy.py: {offenders}"


def test_the_default_is_entra_and_it_is_written_once():
    source = (BACKEND / "application/auth_policy.py").read_text(encoding="utf-8")
    assert source.count('or "entra"') == 1 and "or \"none\"" not in source
    assert auth_policy.auth_mode({}) == "entra"
