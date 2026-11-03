"""The whole frontend gate, one command, one table. Dev tooling.

    python frontend/tools/check_all.py            # everything
    python frontend/tools/check_all.py --quick    # no unit tests, build or sweep

Needs the app reachable: the Vite dev server on :5173 and an API on :8000
(`python frontend/tools/mock_api.py` is enough on a clone without the private
inputs; see tools/README.md). Static checks run regardless.

Each browser check runs in BOTH themes where the theme can change the answer,
and each row says what it compared against. Nothing here is advisory except
what is labelled `info`.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOOLS = Path(__file__).resolve().parent
FRONTEND = TOOLS.parent
REPO = FRONTEND.parent
PY = sys.executable
BASE = "http://localhost:5173"

# Measured before the revamp began (docs/design/UI-STATUS.md, "Baseline"). The
# gate is that none of these gets worse: the partner must still see their data
# without scrolling at 1440x900, the acceptance viewport (desktop only).
BASELINE_TESTS = 600
BASELINE_ROWS = {
    "1440x900": {"portfolio": 7, "client": 13, "unit": 17},
}
TYPE_FLOOR_PX = 12.0

Result = tuple[str, bool, str]


def run(cmd: list[str], env: dict | None = None, cwd: Path = TOOLS, timeout: int = 1500) -> tuple[int, str]:
    merged = {**os.environ, **(env or {})}
    try:
        done = subprocess.run(cmd, cwd=cwd, env=merged, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
    except FileNotFoundError as error:
        return 127, str(error)
    except subprocess.TimeoutExpired:
        return 124, "timed out"
    text = (done.stdout or "") + (done.stderr or "")
    return done.returncode, re.sub(r"\x1b\[[0-9;]*m", "", text)


def reachable() -> bool:
    try:
        urllib.request.urlopen(BASE + "/", timeout=5)
        return True
    except Exception:  # noqa: BLE001
        return False


def tool(script: str, *args: str, theme: str | None = None) -> tuple[int, str]:
    env = {"TCC_THEME": theme} if theme else {}
    return run([PY, script, *args], env=env)


def last(text: str, pattern: str) -> str | None:
    found = re.findall(pattern, text)
    return found[-1] if found else None


def check_tests() -> Result:
    npx = shutil.which("npx") or "npx"
    code, out = run([npx, "vitest", "run"], env={"NODE_OPTIONS": "--no-experimental-webstorage"}, cwd=FRONTEND)
    passed = int(last(out, r"Tests\s+(?:\d+ failed \| )?(\d+) passed") or 0)
    skipped = "skipped" in (last(out, r"(Tests[^\n]*)") or "")
    ok = code == 0 and passed >= BASELINE_TESTS and not skipped
    return "npm test", ok, f"{passed} passed (baseline {BASELINE_TESTS}), skips added: {skipped}"


def check_build() -> Result:
    npm = shutil.which("npm") or "npm"
    code, out = run([npm, "run", "build"], cwd=FRONTEND)
    js = last(out, r"index-[\w-]+\.js\s+([\d.]+ kB)")
    css = last(out, r"index-[\w-]+\.css\s+([\d.]+ kB)")
    return "npm run build", code == 0, f"js {js}, css {css}"


def check_static() -> list[Result]:
    results = []
    code, out = tool("check_tokens.py")
    results.append(("check_tokens", code == 0, last(out, r"check_tokens: ([^\n]+)") or out[-120:]))
    code, out = tool("design_metrics.py")
    raw = last(out, r"raw px font-size \(a bug\): (\d+) distinct")
    results.append(("design_metrics", code == 0 and raw == "0", f"raw px font sizes: {raw}; "
                    f"deprecated aliases: {last(out, r'-> (\d+) uses total')}"))
    return results


def check_type_floor() -> list[Result]:
    results = []
    for theme in ("modern", "classic"):
        code, out = tool("check_type_floor.py", theme=theme)
        smallest = float(last(out, r"smallest rendered data text: ([\d.]+)px") or 0)
        results.append((f"type floor [{theme}]", code == 0 and smallest >= TYPE_FLOOR_PX, f"{smallest}px (floor {TYPE_FLOOR_PX})"))
    return results


def check_rows() -> list[Result]:
    results = []
    for theme in ("modern", "classic"):
        for size, expected in BASELINE_ROWS.items():
            w, h = size.split("x")
            code, out = tool("measure_ui.py", w, h, theme=theme)
            blob = out[out.index("{"):] if "{" in out else "{}"
            try:
                data = json.loads(blob)
            except json.JSONDecodeError:
                results.append((f"visible rows {size} [{theme}]", False, "no measurement"))
                continue
            seen = {page: data[page]["rowsVisibleNoScroll"] for page in expected}
            ok = all(seen[page] >= expected[page] for page in expected)
            results.append((f"visible rows {size} [{theme}]", ok, f"{seen} vs baseline {expected}"))
    return results


def check_browser_pass_fail() -> list[Result]:
    results = []
    code, out = tool("check_brand.py")
    results.append(("check_brand [both themes]", code == 0, last(out, r"check_brand: ([^\n]+)") or "no output"))
    code, out = tool("check_contrast.py")
    results.append(("check_contrast [modern enforced]", code == 0, last(out, r"check_contrast: ([^\n]+)") or "no output"))
    for theme in ("modern", "classic"):
        code, out = tool("check_cell_fit.py", theme=theme)
        clipped = last(out, r"clipped \(text wider than its cell\): (\d+)")
        results.append((f"check_cell_fit [{theme}]", code == 0 and clipped == "0", f"clipped cells: {clipped}"))
        code, out = tool("check_table_width.py", theme=theme)
        results.append((f"check_table_width [{theme}]", code == 0 and "OVERFLOWS" not in out,
                        f"{out.count('OVERFLOWS')} overflowing table(s)"))
        code, out = tool("check_filters.py", theme=theme)
        results.append((f"check_filters [{theme}]", code == 0, "every filter type live" if code == 0 else out[-120:]))
    code, out = tool("check_states.py")
    results.append(("check_states [forced states]", code == 0, last(out, r"(states: [^\n]+)") or "no output"))
    code, out = tool("check_a11y.py")
    results.append(("check_a11y [axe, serious/critical]", code == 0, last(out, r"a11y: ([^\n]+)") or "no output"))
    return results


def check_sweep() -> Result:
    code, out = tool("sweep.py")
    report = TOOLS / "sweep-output" / "sweep-report.md"
    before = TOOLS / "sweep-output" / "before-sweep-report.md"
    fails = int(last(report.read_text(encoding="utf-8") if report.exists() else "", r"\*\*(\d+) FAIL\*\*") or -1)
    base = int(last(before.read_text(encoding="utf-8") if before.exists() else "", r"\*\*(\d+) FAIL\*\*") or fails)
    return "landmine sweep", 0 <= fails <= base, f"{fails} FAIL (baseline {base})"


def check_repo() -> list[Result]:
    results = []
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    if pwsh:
        code, out = run([pwsh, "-NoProfile", "-File", str(REPO / "scripts" / "check-whitelabel.ps1"), "-Enforce"], cwd=REPO)
        results.append(("check-whitelabel -Enforce", code == 0, (out.strip().splitlines() or [""])[-1][:100]))
    code, out = run([PY, str(REPO / "scripts" / "audit-export.py"), "--enforce"], cwd=REPO)
    results.append(("audit-export --enforce", code == 0, (out.strip().splitlines() or [""])[-1][:100]))
    if shutil.which("gitleaks"):
        # Scoped to THIS branch: `detect` alone scans every ref, so another
        # branch's history fails a gate it has nothing to do with. The history
        # of HEAD plus the working tree (`--no-git`, which also sees files not
        # yet committed) covers everything this branch can ship.
        code, out = run(["gitleaks", "detect", "--no-banner", "--redact", "--log-opts=HEAD"], cwd=REPO)
        code2, out2 = run(["gitleaks", "detect", "--no-banner", "--redact", "--no-git"], cwd=REPO)
        ok = code == 0 and code2 == 0
        results.append(("gitleaks (HEAD + working tree)", ok, "no leaks" if ok else (out + out2)[-100:]))
    else:
        results.append(("gitleaks (info)", True, "not installed; skipped"))
    return results


def main() -> int:
    quick = "--quick" in sys.argv
    results: list[Result] = []
    stages: list[tuple[str, object]] = []
    if not quick:
        stages += [("tests", check_tests), ("build", check_build)]
    stages += [("static", check_static)]
    if reachable():
        stages += [("type floor", check_type_floor), ("rows", check_rows), ("browser", check_browser_pass_fail)]
        if not quick:
            stages += [("sweep", check_sweep)]
    else:
        print(f"!! {BASE} is not reachable: start `npm run dev` and an API (tools/README.md). Browser checks skipped.\n")
        results.append(("browser checks", False, "app not reachable"))
    stages += [("repo", check_repo)]

    for name, fn in stages:
        started = time.time()
        print(f"... {name}", flush=True)
        outcome = fn()
        results += outcome if isinstance(outcome, list) else [outcome]
        print(f"    {time.time() - started:.0f}s")

    width = max(len(name) for name, _, _ in results)
    print("\n" + "=" * (width + 60))
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name:<{width}}  {detail}")
    failed = [name for name, ok, _ in results if not ok]
    print("=" * (width + 60))
    print(f"{len(results) - len(failed)}/{len(results)} passed" + (f"; failed: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
