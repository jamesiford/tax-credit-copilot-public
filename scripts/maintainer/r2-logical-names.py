"""One-shot, mechanical: replace physical schema literals in dotnet/src C# with logical names.

Code strings become {ops.x}/{gold.x} tokens (doubled inside interpolated strings), whole-literal table names
become logical keys ("ops.x"), comments say "ops"/"gold". Anything it cannot place is left for a human and
reported, so no repository ends up half-converted silently.
"""
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
SKIP = ("DataMap",)

KEY_LITERAL = re.compile(r'"tcc_(gold|ops)\.([a-z_][a-z0-9_]*)"')
KEY_CONCAT = re.compile(r'"tcc_(gold|ops)\."(\s*\+)')
TOKEN_CONCAT = re.compile(r'tcc_(gold|ops)\."\s*\+\s*([A-Za-z_][A-Za-z0-9_.]*)\s*\+\s*"')
TOKEN = re.compile(r'tcc_(gold|ops)\.([a-z_][a-z0-9_]*)\b')
COMMENT_QUALIFIED = re.compile(r'tcc_(gold|ops)\.')
COMMENT_BARE = re.compile(r'\btcc_(gold|ops)\b')

changed, residual = 0, []
for path in sorted(ROOT.rglob("*.cs")):
    if any(part in SKIP for part in path.parts) or "obj" in path.parts or "bin" in path.parts:
        continue
    original = path.read_text(encoding="utf-8")
    lines = original.split("\n")
    for i, line in enumerate(lines):
        if "tcc_" not in line:
            continue
        stripped = line.lstrip()
        if stripped.startswith("//"):
            line = COMMENT_BARE.sub(r"\1", COMMENT_QUALIFIED.sub(r"\1.", line))
        else:
            line = KEY_LITERAL.sub(r'"\1.\2"', line)
            line = KEY_CONCAT.sub(r'"\1."\2', line)
            braces = ("{{", "}}") if "$" in line.split("tcc_")[0] and '$"' in line or '$"""' in line else ("{", "}")
            line = TOKEN_CONCAT.sub(lambda m: f'{braces[0]}{m.group(1)}." + {m.group(2)} + "{braces[1]}', line)
            line = TOKEN.sub(lambda m: f"{braces[0]}{m.group(1)}.{m.group(2)}{braces[1]}", line)
        lines[i] = line
    updated = "\n".join(lines)
    if updated != original:
        path.write_text(updated, encoding="utf-8", newline="")
        changed += 1
    for n, line in enumerate(lines, 1):
        if re.search(r"tcc_(gold|ops|source)", line):
            residual.append(f"{path.relative_to(ROOT)}:{n}: {line.strip()[:160]}")
print(f"{changed} files changed; {len(residual)} residual lines")
print("\n".join(residual))
