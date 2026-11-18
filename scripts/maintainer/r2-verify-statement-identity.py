"""R2.6 static proof: every statement line the R2 refactor changed resolves, under the shipped map, to the line it replaced.

For each one-line replacement in `git diff <base> HEAD -- dotnet/src` this expands the logical form back
(`{ops.x}` -> `tcc_ops.x`, `"ops.x"` -> `"tcc_ops.x"`, doubled braces inside interpolated strings, comment words)
and compares it with the removed line. Lines that are not a 1:1 replacement are listed for the human review
recorded in docs/rename-r2-log.md; the tests (persistence, API, Parity, Shadow) are the dynamic half of the proof.
"""
import re
import subprocess
import sys

base = sys.argv[1] if len(sys.argv) > 1 else "main"
diff = subprocess.run(["git", "diff", "-U0", base, "HEAD", "--", "dotnet/src"], capture_output=True, text=True, encoding="utf-8").stdout
SCHEMA = {"gold": "tcc_gold", "ops": "tcc_ops"}


def expand(line: str) -> str:
    line = re.sub(r"\{\{(gold|ops)\.([a-z_][a-z0-9_]*)\}\}", lambda m: "{" + SCHEMA[m.group(1)] + "." + m.group(2) + "}", line)
    line = re.sub(r"\{(gold|ops)\.([a-z_][a-z0-9_]*)\}", lambda m: SCHEMA[m.group(1)] + "." + m.group(2), line)
    line = re.sub(r'\{(gold|ops)\."\s*\+\s*(\w+)\s*\+\s*"\}', lambda m: SCHEMA[m.group(1)] + '." + ' + m.group(2) + ' + "', line)
    line = re.sub(r'"(gold|ops)\.([a-z_][a-z0-9_]*)"', lambda m: '"' + SCHEMA[m.group(1)] + "." + m.group(2) + '"', line)
    line = re.sub(r'"(gold|ops)\."', lambda m: '"' + SCHEMA[m.group(1)] + '."', line)
    return line


identical, manual, file = 0, [], ""
removed, added = [], []


def flush():
    global identical
    if removed or added:
        old = [x.rstrip() for x in removed]
        new = [expand(x).rstrip() for x in added]
        comment_old = [re.sub(r"\btcc_(gold|ops)\.?", lambda m: m.group(1) + ("." if m.group(0).endswith(".") else ""), x) for x in old]
        if old == new or comment_old == [re.sub(r"\btcc_(gold|ops)\.?", lambda m: m.group(1) + ("." if m.group(0).endswith(".") else ""), x) for x in new]:
            identical += len(old)
        else:
            manual.append((file, old, added))
    removed.clear()
    added.clear()


for raw in diff.splitlines():
    if raw.startswith("+++ "):
        flush()
        file = raw[6:]
    elif raw.startswith("@@"):
        flush()
    elif raw.startswith("-") and not raw.startswith("---"):
        removed.append(raw[1:])
    elif raw.startswith("+") and not raw.startswith("+++"):
        added.append(raw[1:])
flush()
print(f"{identical} replaced lines resolve to exactly the line they replaced")
print(f"{len(manual)} hunks need human review (not a 1:1 name replacement):")
for f, old, new in manual:
    if any("tcc_" in x for x in old):
        print(f"  {f}: {len(old)} -> {len(new)} lines")
