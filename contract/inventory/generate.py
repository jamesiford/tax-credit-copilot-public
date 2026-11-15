"""Stage C1: generate the surface inventory from the LIVE objects (never from reading source by eye).

    python -m contract.inventory.generate            # write contract/inventory/*
    python -m contract.inventory.generate --check    # exit 1 if the product no longer matches what was written

Every output is a pure function of the product at HEAD: no timestamps, no absolute paths, no machine-specific values,
sorted wherever order is not itself part of the contract (route order and tool order ARE, and are kept).
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import inspect
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from contract.harness import hermetic  # noqa: E402

hermetic.apply()
os.environ["CHANNEL_DEBUG_WHOAMI"] = "0"

BACKEND = ROOT / "backend"
ORCH = ROOT / "channel_orchestrator"


def dump(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def _callable_name(call: Any) -> str:
    module = getattr(call, "__module__", "") or ""
    name = getattr(call, "__qualname__", None) or getattr(call, "__name__", None) or repr(call)
    return f"{module}.{name}"


def _rate_kind(call: Any) -> str | None:
    """`rate_limited(kind)` returns a closure; the kind is the only free variable that is a string."""
    for cell in getattr(call, "__closure__", None) or ():
        if isinstance(cell.cell_contents, str):
            return cell.cell_contents
    return None


def _flatten(dependant: Any, seen: list[dict[str, Any]]) -> None:
    for sub in dependant.dependencies:
        if sub.call is not None:
            entry = {"call": _callable_name(sub.call)}
            kind = _rate_kind(sub.call) if sub.call.__qualname__.endswith("rate_limited.<locals>.check") else None
            if kind:
                entry["rate_limit_kind"] = kind
            seen.append(entry)
        _flatten(sub, seen)


def _params(route: Any) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {"path": [], "query": [], "header": [], "cookie": []}
    d = route.dependant
    for bucket, fields in (("path", d.path_params), ("query", d.query_params), ("header", d.header_params), ("cookie", d.cookie_params)):
        for f in fields:
            out[bucket].append({"name": f.alias or f.name, "required": f.field_info.is_required(), "annotation": str(f.field_info.annotation)})
    return out


def _class_name(cls: Any) -> str:
    cls = getattr(cls, "value", cls)  # FastAPI wraps the default in a DefaultPlaceholder
    return getattr(cls, "__name__", type(cls).__name__)


def _is_model(model: Any) -> bool:
    """A response model that constrains the body: a pydantic model, alone or inside a container/union.

    FastAPI infers `response_model=dict` from a `-> dict` annotation; that constrains nothing, so it is untyped.
    """
    if model is None or model in (dict, list, Any):
        return False
    text = repr(model)
    return text not in ("dict[str, typing.Any]", "list[dict[str, typing.Any]]", "typing.Any") and (
        hasattr(model, "model_fields") or "BaseModel" in text or any(hasattr(a, "model_fields") for a in getattr(model, "__args__", ()))
    )


def _model_name(model: Any) -> str | None:
    if model is None:
        return None
    return getattr(model, "__name__", None) or str(model)


def build_app_surface() -> tuple[dict[str, Any], dict[str, Any]]:
    import main
    from fastapi.openapi.utils import get_openapi

    app = main.app
    openapi = get_openapi(title=app.title, version=app.version, routes=app.routes)
    op_index: dict[tuple[str, str], dict[str, Any]] = {}
    for path, item in openapi.get("paths", {}).items():
        for method, op in item.items():
            op_index[(method.upper(), path)] = op

    from fastapi.routing import APIRoute

    app_level = [{"call": _callable_name(d.dependency)} for d in app.router.dependencies]
    routes: list[dict[str, Any]] = []
    for order, route in enumerate(app.routes):
        if isinstance(route, APIRoute):
            for method in sorted(route.methods - {"HEAD"}) if route.methods else []:
                op = op_index.get((method, route.path), {})
                deps: list[dict[str, Any]] = []
                _flatten(route.dependant, deps)
                declared = sorted({int(k) for k in (op.get("responses") or {}) if k.isdigit()})
                routes.append({
                    "order": order, "method": method, "path": route.path, "name": route.name, "tags": list(route.tags or []),
                    "endpoint": _callable_name(route.endpoint), "parameters": _params(route),
                    "request_body_schema": ((op.get("requestBody") or {}).get("content") or {}),
                    "response_model": _model_name(route.response_model), "status_code": route.status_code or 200,
                    "declared_status_codes": declared, "dependencies": deps, "untyped": not _is_model(route.response_model),
                    "response_class": _class_name(route.response_class),
                })
        else:
            routes.append({"order": order, "method": sorted(getattr(route, "methods", None) or ["GET"]), "path": route.path,
                           "name": getattr(route, "name", None), "framework_route": type(route).__name__, "untyped": True})

    middleware = []
    for m in app.user_middleware:
        middleware.append({"class": f"{m.cls.__module__}.{m.cls.__name__}", "options": {k: v for k, v in sorted(m.kwargs.items())}})
    handlers = []
    for exc, handler in app.exception_handlers.items():
        handlers.append({"exception": f"{exc.__module__}.{exc.__name__}" if inspect.isclass(exc) else str(exc),
                         "handler": _callable_name(handler),
                         "doc": (inspect.getdoc(handler) or "").strip()})
    surface = {
        "title": app.title, "version": app.version, "app_level_dependencies": app_level, "middleware": middleware,
        "exception_handlers": handlers,
        "routes_total": len(routes), "api_routes": sum(1 for r in routes if "framework_route" not in r),
        "untyped_routes": sum(1 for r in routes if r.get("untyped") and "framework_route" not in r),
        "routes": routes,
    }
    return surface, openapi


def _handler_shapes() -> list[dict[str, Any]]:
    """Shapes are recorded exactly in stage C3/C4 recordings; here, what the code says each handler returns."""
    return [
        {"exception": "application.identity.NotAuthorized", "status": 403, "body": {"detail": "<message or 'not authorized'>"}},
        {"exception": "application.errors.DependencyUnavailable", "status": 503, "body": "exc.as_detail() (see recordings)"},
        {"exception": "application.program_defaults.ProgramStateConflict", "status": 422, "body": {"detail": "<message>"}},
        {"exception": "fastapi.exceptions.RequestValidationError", "status": 422, "body": {"detail": [{"type": "", "loc": [], "msg": "", "input": None}]}},
        {"exception": "starlette.exceptions.HTTPException", "status": "any", "body": {"detail": "<str|object>"}},
    ]


def build_channel() -> dict[str, Any]:
    from application.capabilities import catalog
    from channel.app import create_app
    from channel.config import GatewaySettings

    settings = _gateway_defaults()
    gateway = create_app(settings, api=_NullApi(), validator=_NullValidator())
    routes = []
    for r in gateway.routes:
        routes.append({"path": r.path, "methods": sorted(getattr(r, "methods", None) or []), "name": getattr(r, "name", None)})
    tools = []
    for spec in catalog.offered_for_channel(debug=False):
        tools.append({
            "name": spec.name, "description": spec.description, "kind": getattr(spec, "kind", None),
            "channel_description": catalog.channel_description(spec) if hasattr(catalog, "channel_description") else None,
            "schema": spec.schema, "model_schema": catalog.model_schema(spec),
            "hints": catalog.behaviour_hints(spec) if hasattr(catalog, "behaviour_hints") else None,
        })
    debug_tools = [s.name for s in catalog.offered_for_channel(debug=True)]
    from channel.mcp import McpServer

    mcp_source = inspect.getsource(McpServer)
    methods = sorted(set(re.findall(r'"((?:initialize|ping|tools/\w+|notifications/\w+|resources/\w+|prompts/\w+|logging/\w+))"', mcp_source)))
    return {"gateway_routes": routes, "pinned_route_inventory_file": rel(BACKEND / "tests" / "channel_route_inventory.json"),
            "jsonrpc_methods_named_in_source": methods, "tools_count": len(tools), "tools_count_with_debug": len(debug_tools),
            "debug_only_tools": sorted(set(debug_tools) - {t["name"] for t in tools}), "tools": tools}


class _NullApi:
    async def close(self) -> None:  # pragma: no cover - inventory only builds the app
        return None


class _NullValidator:
    def validate(self, token):  # pragma: no cover
        raise RuntimeError("inventory does not authenticate")


def _gateway_defaults():
    """Gateway settings from a throwaway synthetic mapping (all-zero GUID tenant; no real value)."""
    from channel.config import load_settings

    return load_settings({
        "TENANT_ID": "00000000-0000-0000-0000-000000000001", "GATEWAY_AUDIENCE": "api://contract-gateway",
        "API_BASE_URL": "http://api.invalid", "API_AUDIENCE": "api://contract-api", "ENVIRONMENT": "local",
    })

def build_orchestrator() -> dict[str, Any]:
    sys.path.append(str(ORCH))
    from app.core import prompts as orch_prompts
    from app.core.tools import model_tools, offered_schema

    tools = [{"name": n, "description": s.description, "schema_offered_to_model": offered_schema(s)} for n, s in model_tools().items()]
    texts = {}
    for name in dir(orch_prompts):
        value = getattr(orch_prompts, name)
        if name.isupper() and isinstance(value, str) and len(value) > 40:
            texts[name] = {"sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(), "text": value}
    host_src = (ORCH / "app" / "host.py").read_text(encoding="utf-8")
    return {
        "http_surface": {
            "responses_handler": "app.main.create_host registers one `response_handler` on azure.ai.agentserver.responses.ResponsesAgentServerHost "
                                  "(the Responses protocol on port 8088; the hosting package owns the HTTP framing)",
            "readiness": "provided by the host package (`/readiness`)",
            "text_commands": sorted(set(re.findall(r'"(/(?:whoami|netcheck|modelprobe))"', host_src))),
            "debug_gate": "CHANNEL_DEBUG_WHOAMI (the commands are only honoured when it is on)",
            "other_routes": "none defined in channel_orchestrator/; see docs below",
        },
        "files": {rel(p): sha256(p) for p in sorted((ORCH / "app").rglob("*.py"))},
        "tools_offered_to_a_model_count": len(tools), "tools_offered_to_a_model": tools, "prompt_texts": texts,
        "narrator_prompt_file": rel(BACKEND / "agents" / "prompts" / "channel_narrator.md"),
    }


def build_agents() -> dict[str, Any]:
    agents_dir = BACKEND / "agents"
    prompts = sorted((agents_dir / "prompts").glob("*.md"))
    from infrastructure.ai.prompt_manifest import check, load_manifest
    from infrastructure.ai.prompts_fs import FilePromptStore
    import infrastructure.ai.prompt_manifest as pm

    return {
        "agents_json": json.loads((agents_dir / "agents.json").read_text(encoding="utf-8")),
        "prompt_files": {p.name: {"sha256": sha256(p), "bytes": p.stat().st_size} for p in prompts},
        "prompt_count": len(prompts),
        "manifest": json.loads((agents_dir / "prompts" / "manifest.json").read_text(encoding="utf-8")),
        "manifest_check_today": check(FilePromptStore(), load_manifest()),
        "manifest_check_enforces": (inspect.getdoc(pm) or "").strip(),
    }


_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")


def _env_reads(tree: ast.AST) -> set[str]:
    found: set[str] = set()

    def is_env(node: ast.AST) -> bool:
        text = ast.unparse(node)
        return "environ" in text or text in {"env", "os.environ", "mapping", "settings_env"} or text.endswith("environ")

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = ast.unparse(node.func)
            if func in ("os.getenv", "getenv") and node.args and isinstance(node.args[0], ast.Constant):
                found.add(str(node.args[0].value))
            elif isinstance(node.func, ast.Attribute) and node.func.attr in ("get", "pop", "setdefault") and is_env(node.func.value):
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    found.add(node.args[0].value)
            elif any(is_env(a) for a in node.args[:1]):
                for a in node.args[1:2]:
                    if isinstance(a, ast.Constant) and isinstance(a.value, str):
                        found.add(a.value)
        elif isinstance(node, ast.Subscript) and is_env(node.value) and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            found.add(node.slice.value)
    return {n for n in found if _ENV_NAME.match(n)}


def build_env() -> dict[str, Any]:
    reads: dict[str, set[str]] = {}
    roots = [BACKEND, ORCH]
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            parts = path.relative_to(ROOT).parts
            if "tests" in parts or "vendor" in parts or ".venv" in parts or "__pycache__" in parts:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for name in _env_reads(tree):
                reads.setdefault(name, set()).add(rel(path))
    doc = (ROOT / "docs" / "architecture" / "ENV-VARS.md").read_text(encoding="utf-8")
    documented = set(re.findall(r"`([A-Z][A-Z0-9_]{2,})`", doc))
    code = set(reads)
    return {
        "method": "AST scan of backend/ and channel_orchestrator/ (tests and vendored copies excluded) for os.getenv(NAME), "
                  "os.environ[NAME], <environ-like>.get(NAME), and any call whose first argument is an environ-like mapping and "
                  "whose second is the NAME (config helpers such as tuned_int(environ, NAME, ...)); documented names are every "
                  "back-ticked UPPER_SNAKE token in docs/architecture/ENV-VARS.md",
        "read_by_code": {k: sorted(v) for k, v in sorted(reads.items())},
        "read_by_code_count": len(code),
        "documented_count": len(documented),
        "read_but_not_documented": sorted(code - documented),
        "documented_but_not_read": sorted(documented - code),
    }


def _ddl_tables(sql: str) -> dict[str, list[str]]:
    tables: dict[str, list[str]] = {}
    for m in re.finditer(r"CREATE TABLE\s+(\w+\.\w+)\s*\((.*?)\n\)\s*;?", sql, re.DOTALL | re.IGNORECASE):
        cols = []
        for line in m.group(2).splitlines():
            line = line.strip().rstrip(",")
            if not line or line.startswith(("--", "CONSTRAINT", "PRIMARY", "FOREIGN", "UNIQUE", "CHECK")):
                continue
            head = line.split()[0].strip("[]")
            if re.match(r"^\w+$", head):
                cols.append(line.split("--")[0].strip())
        tables[m.group(1)] = cols
    return tables


def build_data() -> dict[str, Any]:
    schema_dir = ROOT / "docs" / "data" / "schema"
    sql_files = sorted(schema_dir.glob("*.sql")) + sorted((schema_dir / "migrations").glob("*.sql"))
    ddl = _ddl_tables((schema_dir / "tcc-schema.sqlserver.sql").read_text(encoding="utf-8"))
    from tools import gold_projection as gp

    code_expectation = {n[: -len("_COLUMNS")].lower(): list(getattr(gp, n)) for n in sorted(dir(gp)) if n.endswith("_COLUMNS") and isinstance(getattr(gp, n), (tuple, list))}
    from infrastructure.persistence.fabric_warehouse import _MANIFEST_COLUMNS

    code_expectation["run_manifest"] = list(_MANIFEST_COLUMNS)
    rules = {rel(p): sha256(p) for p in sorted((BACKEND / "rules").rglob("*")) if p.is_file()}
    return {
        "sql_files": {rel(p): sha256(p) for p in sql_files},
        "tables_in_sqlserver_ddl": {k: ddl[k] for k in sorted(ddl)},
        "tables_in_sqlserver_ddl_count": len(ddl),
        "columns_the_code_expects": {k: code_expectation[k] for k in sorted(code_expectation)},
        "rules_files": rules, "rules_files_count": len(rules),
    }


def build_all() -> dict[str, str]:
    surface, openapi = build_app_surface()
    surface["exception_handler_shapes"] = _handler_shapes()
    outputs = {
        "routes.json": dump(surface), "openapi.json": dump(openapi), "channel.json": dump(build_channel()),
        "orchestrator.json": dump(build_orchestrator()), "agents.json": dump(build_agents()),
        "env-inventory.json": dump(build_env()), "data.json": dump(build_data()),
    }
    outputs["../CONTRACT-INVENTORY.md"] = render_markdown(surface, json.loads(outputs["channel.json"]), json.loads(outputs["orchestrator.json"]),
                                                          json.loads(outputs["agents.json"]), json.loads(outputs["env-inventory.json"]), json.loads(outputs["data.json"]))
    return outputs


# Routes that cannot be exercised hermetically, with the reason. Everything else is reachable under P1/P2.
NOT_HERMETIC = {
    "/api/chat": "streams a model answer; hermetically the provider chain degrades to scripted text (recorded as such), the model path itself is out of scope",
    "/api/summary": "page-summary narration needs a model; recorded through the scripted fallback and the event-stream framing only",
}


def render_markdown(surface, channel, orch, agents, env, data) -> str:
    api = [r for r in surface["routes"] if "framework_route" not in r]
    lines = ["# Contract inventory", "", "Generated by `python -m contract.inventory.generate` from the live objects. Do not edit by hand.", ""]
    lines += ["## Totals", "", "| Surface | Count |", "|---|---|"]
    lines += [f"| Registered Starlette routes (incl. framework docs/openapi) | {surface['routes_total']} |",
              f"| API operations (method + path) | {len(api)} |",
              f"| API operations without a `response_model` (untyped) | {surface['untyped_routes']} |",
              f"| API operations declaring a `response_model` | {len(api) - surface['untyped_routes']} |",
              f"| Distinct API paths | {len({r['path'] for r in api})} |",
              f"| Channel gateway tools (`tools/list`, debug off) | {channel['tools_count']} |",
              f"| Channel gateway tools (debug on) | {channel['tools_count_with_debug']} |",
              f"| Tools offered to a model by the orchestrator | {orch['tools_offered_to_a_model_count']} |",
              f"| Agent prompt files | {agents['prompt_count']} |",
              f"| Environment variables read by code / documented | {env['read_by_code_count']} / {env['documented_count']} |",
              f"| Tables in the SQL Server DDL | {data['tables_in_sqlserver_ddl_count']} |",
              f"| Rule-pack files hashed | {data['rules_files_count']} |", ""]
    lines += ["## Middleware and handlers", ""]
    for m in surface["middleware"]:
        lines.append(f"- `{m['class']}` {json.dumps(m['options'], sort_keys=True)}")
    for h in surface["exception_handlers"]:
        lines.append(f"- handler `{h['exception']}` -> `{h['handler']}`")
    lines += ["", "## Methods by tag", ""]
    by_tag: dict[str, int] = {}
    for r in api:
        by_tag[(r["tags"] or ["(none)"])[0]] = by_tag.get((r["tags"] or ["(none)"])[0], 0) + 1
    lines += [f"- {k}: {v}" for k, v in sorted(by_tag.items())]
    lines += ["", "## Routes that cannot be exercised fully hermetically", ""]
    for path, why in NOT_HERMETIC.items():
        lines.append(f"- `{path}`: {why}")
    lines += ["", "## Environment variables: code versus docs", "",
              f"- read by code but not documented in ENV-VARS.md: {len(env['read_but_not_documented'])}",
              f"- documented but not found by the scan: {len(env['documented_but_not_read'])} (the scan is static; see `env-inventory.json` `method`)",
              "", "## Orchestrator HTTP surface", "", json.dumps(orch["http_surface"], indent=2), ""]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    outputs = build_all()
    bad = []
    for name, text in outputs.items():
        target = (HERE / name).resolve()
        if args.check:
            if not target.exists() or target.read_text(encoding="utf-8") != text:
                bad.append(rel(target))
        else:
            target.write_text(text, encoding="utf-8", newline="\n")
    if args.check:
        if bad:
            print("inventory is stale: " + ", ".join(bad))
            return 1
        print(f"inventory matches the product ({len(outputs)} files)")
        return 0
    print(f"wrote {len(outputs)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
