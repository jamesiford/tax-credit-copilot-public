"""One-shot, mechanical: `{GOLD_SCHEMA}.table` / `{OPS_SCHEMA}.table` -> `{names.gold.table}` / `{names.ops.table}`.

Names only. Where a file used the schema constants only for table references, ruff then drops the
now-unused import. Files this cannot place (a schema used as a bare value) are reported, not guessed at.
"""
import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
SKIP = {"backend/config.py", "backend/data_map.py", "backend/data_map_load.py"}
LITERAL = re.compile(r"\{(GOLD|OPS)_SCHEMA\}\.([a-z][a-z0-9_]*)")
DYNAMIC = re.compile(r"\{(GOLD|OPS)_SCHEMA\}\.\{(\w+)\}")
KIND = {"GOLD": "gold", "OPS": "ops"}

files = subprocess.run(["git", "ls-files", "*.py"], capture_output=True, text=True, cwd=ROOT).stdout.split()
changed, notes = [], []
for rel in files:
    if rel in SKIP or rel.startswith("backend/tests/"):
        continue
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    new = DYNAMIC.sub(lambda m: "{names.%s(%s)}" % (KIND[m.group(1)], m.group(2)), text)
    new = LITERAL.sub(lambda m: "{names.%s.%s}" % (KIND[m.group(1)], m.group(2)), new)
    if new == text:
        continue
    lines = new.split("\n")
    placed = False
    for node in ast.walk(ast.parse(new)):
        if isinstance(node, ast.ImportFrom) and any(a.name in ("GOLD_SCHEMA", "OPS_SCHEMA") for a in node.names):
            first = lines[node.lineno - 1]
            indent = first[: len(first) - len(first.lstrip())]
            tail = "  # noqa: E402" if "noqa: E402" in lines[node.end_lineno - 1] else ""
            lines.insert(node.end_lineno, f"{indent}from config import names{tail}")
            placed = True
            break
    if not placed:
        notes.append(f"{rel}: replaced tokens but found no schema import to anchor `names`")
    path.write_text("\n".join(lines), encoding="utf-8", newline="")
    changed.append(rel)
print(f"{len(changed)} files changed")
print("\n".join(notes))
print("\n".join(changed))
