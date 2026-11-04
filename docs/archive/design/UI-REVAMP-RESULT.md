# UI revamp: result

What the modern-theme revamp (UI-01 to UI-08) changed, what it deliberately did
not, where the doctrine moved, the before/after numbers, and what is still open.
The reference is [DESIGN-SYSTEM.md](../../design/DESIGN-SYSTEM.md); every choice has its
reasoning in [UI-DECISIONS.md](../../design/UI-DECISIONS.md) (D1 to D34); work package
history is in [UI-STATUS.md](../../design/UI-STATUS.md). Nothing here was pushed.

## What changed

| Area | Before | After |
| --- | --- | --- |
| Look | One hand-rolled stylesheet, three accents, 23 type sizes, 17 radii | Token layers (primitive → role → component) and two themes: **modern** (default) and **classic** (the previous look, `VITE_THEME=classic`) |
| Shell | Left rail, per-page breadcrumb | Top bar with three dropdown groups, a drill trail derived from the route, one floating Ask launcher |
| Home | The book | A hero and four task cards, then the book |
| Portfolio | A grid and a map above it | A dashboard of cards: the book with band tabs that carry counts, a footprint card, position tiles |
| Client | A row of tabs | A review flow: header with meta, a route-driven stepper, verdict cards for programmes and findings |
| Ask | A 420px chat drawer, plus an Ask button in two page headers | A modal workspace: conversation beside the evidence it came from; one launcher |
| States | A mix of callouts, "Loading…" strings and blank panels | `Skeleton`, `EmptyState` and a named "Scope adjusted" banner; every state forced and checked |
| Accessibility | Not measured | axe-core gate, zero serious/critical, both themes |
| Type delivery | woff + woff2 of every face, no fallback metrics | woff2 only, metric-matched fallback faces, two preloads |
| Colour vocabulary | `--accent*`, `--accent-2*`, `--exp-*` read by components (233 uses) | Roles only; the ratchet is at 0 |

## What deliberately did not change

- **`backend/`, the parity pins and every statutory figure.** This is a skin,
  a shell and a conversation surface. No figure is computed in the browser; the
  evidence pane renders strings it was given.
- **The 67 routes and the API.** `tests/route_inventory.json` is untouched.
- **The data grids stay dense** (12px, 28px rows). The visible-row gate at
  1440×900 is held at the pre-revamp 7 / 13 / 17.
- **The classic theme's palette.** It is the rollback, so its contrast
  shortfalls are reported, not fixed (D9).
- **The sealed views** (parity run, methodology) still do not follow the
  client selector; they are labelled as such.
- **The deprecated aliases are still defined**, so a customer overlay written
  against them keeps resolving (D30).
- **No mobile layout.** Desktop at 1440×900 is the acceptance viewport; 1024×768
  is a smoke check (nothing overflows, everything is reachable).
- **No charts, no reminders, no alerts.** The app holds no series or events to
  draw them from (D20).

## Doctrine that moved

These are the places the written rules in `.github/copilot-instructions.md` and
the design system now say something different from before the revamp.

1. **Navigation is a top bar and a drill trail, not a rail.** (D14, D15)
2. **Two jobs, two treatments.** Selection is the brand blue; a reading
   (figure, status, verdict) is navy plus `--state-*`. They never swap, and
   `check_brand.py` fails if a verdict computes to a selection colour. Purple is
   now an optional overlay accent, not a requirement.
3. **Two density registers.** Chrome is comfortable; data is 12px / 28px and no
   theme changes that.
4. **Type is a scale of eight, a spacing scale of sixteen, a radius scale of
   five, and a raw `px` in any of them is a bug.** Half-pixel sizes are
   always a bug.
5. **The typeface is self-hosted, woff2 only, with fallback faces**, and no
   request may leave the origin (the map geometry is vendored).
6. **A conversation has evidence beside it**, typed, validated, dropped and
   counted when malformed, and never repaired.
7. **An accessibility, state and performance check is part of "done"**, not a
   later pass.
8. **A declined scope is said on the page**, not in a tooltip.

## Numbers

Measured against the offline stand-in (a mock API forwarding to a real backend
on `DATA_SOURCE=csv`), so counts are relative, not product figures.

| Metric | Before the revamp | Now |
| --- | --- | --- |
| `npm test` | 600 passed | **923 passed**, 79 files, no skips added |
| JS bundle | 664.14 kB | 700.44 kB (+5.5%: the Ask workspace and the evidence contract) |
| CSS bundle | 134.97 kB (+ Roboto 400-800 as woff and woff2) | **125.89 kB**, woff2 only (142 kB of fonts, 0 woff) |
| `index.css` | 2702 lines at UI-04 | **1447 lines** |
| Deprecated alias uses | 233 | **0** |
| Raw-px font sizes / half-pixel / raw-px padding | 0 / 0 / 5 | **0 / 0 / 0** |
| Inline `style={{ }}` | 2 | 2 (the two documented exceptions) |
| Visible rows 1440×900 (portfolio / client / unit) | 7 / 13 / 17 | **7 / 13 / 17**, both themes |
| Smallest rendered data text | 12.0px | 12.0px, both themes |
| Cells clipped / tables overflowing | 0 / 0 | 0 / 0, both themes |
| `check_contrast` (modern) | not gated | 0 pairs below AA |
| axe serious/critical | not measured | **0**, both themes (classic contrast reported) |
| Forced states (`check_states`) | not measured | **37 / 37** |
| Font-swap layout shift | not measured | 0.001 to 0.002 (gate 0.10) |
| Off-origin requests | the map geometry was hotlinked | **none** (`check_brand` fails on one) |
| Landmine sweep | 44 FAIL, 5 WARN | no more FAIL than the stored baseline (the stand-in's limits) |

## Known gaps

- **The client page shifts layout while its data loads** (CLS about 0.49 on the
  stand-in). It is data-driven, not font-driven, predates this work, and the
  fix is reserving the grid's height from the unit count the page already
  holds. Not done: it needs the real backend's timings to tune.
- **Moderate axe findings are reported, not gated**: `landmark-unique` and
  `landmark-no-duplicate-banner` on the shell header and repeated specimen navs,
  `heading-order` where a page starts on an `h2`.
- **Classic `color-contrast`** is reported, by decision (D9).
- **`/api/workspace/*` sub-endpoints answer 503 on the stand-in**, so the sealed
  Evidence page's panels render their unavailable state there. Check that page
  against the real backend.
- **The evidence stream is front end only.** Nothing emits an `evidence` event
  yet; the pane is exercised by the dev fixture (`?askFixture=1`), and the
  confirmation card is inert until a write flow exists (D28).
- **`dead_css.mjs` cannot see a class built at run time** with no recognisable
  prefix. A rule it removed that something needed would show as a visual
  difference in the contact sheet. Of the 45 pairs, seven changed by more than 2%
  against UI-06; the ones inspected (client, payroll data, what-if) were the
  intended changes, the header alignment fix and a corrected what-if shot, not
  missing styles. It is a check, not a proof.
- **`check_perf.py` needs the preview server**, so it is not in `check_all.py`.
- **1024×768 is smoke only.** The portfolio shows 5 rows and the client 9 there;
  nothing overflows.

## Owner review checklist

Screenshots are in the gitignored `frontend/tools/sweep-output/` (they may render
data and are never committed). `after-modern/` and `after-classic/` hold every
routed page, the Ask workspace on each, the fixture conversation and evidence
pane, and the styleguide, at 1024×768 and 1440×900 (index: `after/index.md`). The contact sheet is
`compare-final-modern-vs-after-modern.html` (UI-06 → now); `compare-before-vs-after-modern.html` is the whole revamp (`before/` is the
pre-revamp set).

Look at these first (`after-modern/`, 1440):

1. `portfolio-1440.png`: the dashboard.
2. `client-1440.png`: the review header, stepper and location grid.
3. `unit-1440.png`: the dense grid, the one with the fold gate.
4. `ask-client-1440.png`: the workspace over a client page.
5. `askfx-conversation-1440.png`: conversation and evidence side by side
   (`askfx-evidence-1024.png` is the tabbed layout below 1280px).
6. `rules-1440.png` (Programs): verdict cards.
7. `agents-1440.png`: findings as verdict cards.
8. `eligibility-1440.png`.
9. `employee-1440.png`: the calculation walk.
10. `styleguide-1440.png`: every shared component in one place.

Then the same ten in `after-classic/`, to confirm the rollback still looks like
the old product. And the 1024 smoke set for overflow.

Decisions to confirm or overrule:

- **D5 / D29:** Poppins for chrome, Roboto for data, self-hosted.
- **D1 / D3 / the two-job rule:** the brand blue is selection only; base year is
  sky blue, below-minimum is red, and they must never converge.
- **D6 / D7 and the density registers:** chrome comfortable, data at 12px / 28px.
- **Theme default:** modern is the default; classic is `VITE_THEME=classic`.
- **D14:** the top bar and drill trail instead of the rail.
- **D27:** the Ask workspace is a modal, not a drawer.
- **D30:** the aliases stay defined though nothing reads them.

Run it:

```pwsh
cd frontend
npm run dev                          # modern, http://localhost:5173
$env:VITE_THEME='classic'; npm run dev    # the previous look
python tools\check_all.py            # the whole gate
```

The dev-only styleguide is at `/__styleguide`, and `?askFixture=1` shows the
evidence pane without a backend that emits it.
