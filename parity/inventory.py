"""Import-graph inventory for the .NET domain slice (stage DS1).

Walks every module in ``backend/domain``, ``backend/tools`` and the
application modules that sit on a calculation path, records its line count,
its first-party imports and the I/O-signalling imports it carries, and emits
``--json`` for the port map. Classification is heuristic evidence; the final
verdicts live in ``dotnet/docs/port-map.md``.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
FIRST_PARTY = {p.name for p in BACKEND.iterdir() if p.is_dir() and (p / "__init__.py").exists()}
FIRST_PARTY |= {p.stem for p in BACKEND.glob("*.py")}
IO_SIGNALS = {
    "pyodbc", "requests", "httpx", "aiohttp", "fastapi", "starlette", "azure", "deltalake",
    "pyarrow", "openpyxl", "sqlite3", "subprocess", "socket", "urllib", "agent_framework",
    "pandas", "boto3", "pydantic", "uvicorn", "asyncio", "http", "xlsxwriter", "openai",
}


def module_name(path: Path) -> str:
    rel = path.relative_to(BACKEND).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def scan(path: Path) -> dict:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    mod = module_name(path)
    pkg = mod if path.name == "__init__.py" else mod.rpartition(".")[0]
    internal: set[str] = set()
    external: set[str] = set()
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = pkg.split(".")
                base = base[: len(base) - (node.level - 1)] if node.level > 1 else base
                names = [".".join([*base, *(node.module.split(".") if node.module else [])])]
                if not node.module:
                    names = [f"{names[0]}.{a.name}" for a in node.names]
            elif node.module:
                names = [node.module]
        for n in names:
            (internal if n.split(".")[0] in FIRST_PARTY else external).add(n)
    return {
        "module": mod,
        "path": str(path.relative_to(BACKEND)).replace("\\", "/"),
        "lines": len(src.splitlines()),
        "internal": sorted(internal),
        "io": sorted({e.split(".")[0] for e in external} & IO_SIGNALS),
        "external": sorted({e.split(".")[0] for e in external}),
        "has_main": "__main__" in src,
        "functions": sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for n in tree.body),
        "classes": sum(isinstance(n, ast.ClassDef) for n in tree.body),
    }


def resolve(name: str, index: dict[str, dict]) -> str | None:
    parts = name.split(".")
    while parts:
        cand = ".".join(parts)
        if cand in index:
            return cand
        parts.pop()
    return None


def reachable(roots: list[str], index: dict[str, dict]) -> set[str]:
    seen: set[str] = set()
    stack = [r for r in roots if r in index]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        for imp in index[cur]["internal"]:
            tgt = resolve(imp, index)
            if tgt and tgt not in seen:
                stack.append(tgt)
    return seen


def main() -> int:
    mods = [scan(p) for p in sorted(BACKEND.rglob("*.py")) if "tests" not in p.parts and "__pycache__" not in p.parts]
    index = {m["module"]: m for m in mods}
    for m in mods:
        m["calls_into_domain_or_tools"] = any(i.startswith(("domain", "tools")) for i in m["internal"])
    calc_roots = ["application.commands.run_client_calculation"]
    on_calc = reachable(calc_roots, index)
    cmd_roots = [m for m in index if m.startswith(("application.commands.", "application.queries."))]
    on_any = reachable(cmd_roots, index)
    for m in mods:
        m["on_calc_path"] = m["module"] in on_calc
        m["on_command_or_query_path"] = m["module"] in on_any
    json.dump(mods, sys.stdout, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
