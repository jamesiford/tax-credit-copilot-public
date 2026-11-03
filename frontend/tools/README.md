# Frontend dev tools

Dev tooling, not shipped. Every browser tool drives a real Chromium against the
running app and reads **computed** styles, because a CSS declaration proves
nothing if a fallback wins.

## Running them

```pwsh
cd frontend ; npm install --legacy-peer-deps
pip install playwright ; python -m playwright install chromium
npm run dev                                  # http://localhost:5173
python tools/check_all.py                    # the whole gate
```

The app needs an API on `:8000` (Vite proxies `/api` there). With the private
inputs, run the backend (`backend/`, `python -m uvicorn main:app --port 8000`).
**On a clone without them** the shell cannot boot (it needs the sealed reference
workspace) and every per-client read needs the Fabric Warehouse, so use the
offline stand-in:

```pwsh
python tools/mock_api.py 8000                # serves a small SYNTHETIC dataset
# optional: a real backend on :8001 (DATA_SOURCE=csv) answers everything else
```

`mock_api.py` serves invented data (no payroll, no real names, no certified
figure); it exists only so the gates have a rendered page.

Node 26 enables an experimental `localStorage` that shadows jsdom's. Run the
unit tests with `NODE_OPTIONS=--no-experimental-webstorage` on Node ≥ 25
(`check_all.py` does); the supported runtime is Node 24.

## Themes

Every browser tool honours `TCC_THEME=modern|classic` (via `_theme.py`, which
writes `localStorage['tcc-theme']` before the app boots).

## The tools

| Tool | What it proves |
| --- | --- |
| `check_all.py` | Runs everything below and prints one table; `--quick` skips tests, build and sweep. |
| `measure_ui.py [w h]` | Visible rows and first-row y per page at 1440×900 (the acceptance viewport; mobile is out of scope). The gate: **never fewer visible rows than the baseline**. |
| `check_type_floor.py` | Rendered data text is ≥ 12px. |
| `check_brand.py` | Per theme: computed fonts, every `--state-*` token resolves, base-year vs below-min distance (CIE76), selection ≠ any state colour, no request leaves the origin. |
| `check_contrast.py` | WCAG contrast of rendered text/background pairs; fails < 4.5:1 (3:1 large). Enforced for modern; classic is reported only. |
| `check_tokens.py` | Static: no literal colour or raw `px` spacing/size in `components/ui/*.css`; no `style={{` outside the two documented exceptions. |
| `design_metrics.py` | Type steps in use, raw px, radii, inline styles, deprecated-alias counts. |
| `check_cell_fit.py`, `check_table_width.py` | No figure wider than its cell; the widest grid still fits 1024px. |
| `check_filters.py` | Every filter type is live in the UI. |
| `sweep.py` | The landmine sweep: every reachable state renders or says plainly why not. Compared with `sweep-output/before-sweep-report.md`. |
| `shoot_pages.py <label> [theme]` | Screenshots of every routed page at both viewports into the gitignored `sweep-output/`. |

Repo checks that `check_all.py` also runs: `pwsh scripts/check-whitelabel.ps1
-Enforce`, `python scripts/audit-export.py --enforce`, and `gitleaks` if it is
installed. Screenshots go to `sweep-output/`, which is gitignored: they may
render data and must never be committed.
