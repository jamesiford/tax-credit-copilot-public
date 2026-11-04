import ast, sys
from pathlib import Path

for base in ("backend/application", "backend/channel", "channel_orchestrator/app"):
    for p in sorted(Path(base).rglob("*.py")):
        if {"vendor", "__pycache__"} & set(p.parts):
            continue
        tree = ast.parse(p.read_text(encoding="utf-8"))
        def visit(node, prefix=""):
            for n in ast.iter_child_nodes(node):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not n.name.startswith("_") and not ast.get_docstring(n) and not any(
                        isinstance(d, ast.Name) and d.id in {"property"} for d in n.decorator_list):
                        end = (n.end_lineno or n.lineno) - n.lineno + 1
                        print(f"{p.as_posix()}:{n.lineno} {prefix}{n.name} ({end} lines)")
                elif isinstance(n, ast.ClassDef):
                    visit(n, prefix + n.name + ".")
        visit(tree)
