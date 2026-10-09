# UI revamp — run report

> **Schema v2.0 (Platform v2):** the Warehouse schemas are now `tcc_gold` and `tcc_ops` (were the v1 `flex_*` schemas), configurable via `GOLD_SCHEMA` / `OPS_SCHEMA`. See `docs/data/schema/tcc-schema.fabric.sql`.

Run date: 8 September 2026. Branch `revamp/phase-7-wip`, `7cae036` → `1b7ea37`.
Not merged to main; a human reviews the diff before it lands.

**Outcome: the gate PASSES on every checked item. Seven tests remain red, the
same seven as the first run. Two items of the third follow-up are not done.**

`main` was merged in first (`3a4c1f9`) so the warehouse keepalive fix
(`1aa95fa`) is not lost. Only `docs/design/REVAMP-REPORT.md` conflicted, add/add
as predicted; the branch version was kept because it is the current one.

---

## Round 3 — year, method, sort

### Gate

| Check | Result |
| --- | --- |
| year selector absent on `/c/2001` | **absent** |
| year selector present on unit and portfolio | **present** |
| method absent from the top strip | **absent on all three pages** |
| method reachable on the page | **present on the client page**; see gap below |
| sorting reorders the grid | `TY2020…TY2025` → `TY2025…TY2020` |
| sorting changes the URL | `?year=2023` → `?year=2023&sort=tax_year%3Adesc` |
| sortable headers on the client grid | 30 |

Row counts did not regress:

| Page | Required | Measured |
| --- | --- | --- |
| `/` | all 5 client rows | **5** of 6 |
| `/c/2001?year=2023` | ≥ 12 | **12** of 37 |
| `/c/2001/u/GA_GA-010…` | ≥ 10 | **11** of 33 |

First data row: portfolio 491, client 330, unit 457. Content width 1024 on all
three. `npm run build` passes. `git diff backend/domain/calculation/` empty.

### What changed

- **Year is contextual, not deleted.** `TopScope` renders nothing unless the
  page is portfolio, unit or employee. It stays in the URL, so a year still
  carries down the drill. Absent rather than disabled — a greyed control still
  asks to be clicked.
- **Method left the chrome** and is a labelled tab group at the top of the
  client grid, captioned *"not expected to agree"*. As a top-strip dropdown it
  read as a display preference, and Min-Max against Pay Period is 539 eligible
  employees against 656.
- **The client grid sorts.** Click a header, shift-click to add a second key.
  Sort and the unit filter live in the query string, so a driven view is
  shareable and survives a refresh. `lib/gridSort.js` is framework-free with 14
  unit tests.
- Controls share the title line. A second control band cost exactly one row of
  data, which measured 12 → 11.

### Gap: method is not reachable on the unit page

Method left the top strip, and only the client grid gained a local control. The
unit page reads `method` from the URL but offers no way to change it. A shared
link still reproduces the reading, so nothing is lost — but a person on the unit
page cannot switch. Not fixed; it needs the same tab group.

### Not done

- **The unit cards are still cards** (item 4). The tranche chips and the
  narrative sentence both have to survive the move to a grid row, and I did not
  have room to do that and verify it.
- **No server-side sort/filter on `/api/v2/clients/{id}/units/{unit_id}`**
  (item 3, the one backend change). Candle Bottle's 10,236 employees across 101
  units still cannot be sorted.
- **The portfolio headers are not wired** to the sort/order parameters
  `/api/v2/portfolio` already accepts.

### The previous round's tier work — partly moot, as warned

The overlap warning was right about one half and not the other:

- **Moot:** moving the tier pill into the unit card header. That card is what
  item 4 replaces, so the placement will move again. The *rule* survives — tier
  is a property of the unit, shown once, with the per-year column returning only
  when a year differs.
- **Not moot:** the mid-table header row. That was my own CSS — I had set
  `position: sticky; top: 52px` globally, and these tables live inside
  `.tbl-scroll`, so sticky resolved against that box and pushed the header 52px
  down, below the first row. `top: 0` fixes it and applies to any table.

---

## Round 2 — the months were one year deep

The brief's diagnosis pointed at the read path. It was the **write** path, and
the read needed no change at all:

```
unit_month_summary   TY2023 only          6 rows   (live run)
unit_year_master     TY2020..TY2025      36 rows   (same run)
```

`_replay_unit_series` replays every year and wrote `unit_year_master` for all of
them; `unit_month_summary` was written only from the requested year's result. So
five years of six showed an average against twelve em dashes, which reads as
missing data.

Fixed at the writer, and Cascade re-run to backfill (152s):

```
items  by year: {2020: 6, 2021: 6, 2022: 6, 2023: 6, 2024: 6, 2025: 6}
months by year: {2020: 6, 2021: 6, 2022: 6, 2023: 6, 2024: 6, 2025: 6}
```

The requested year's month rows are still the ones computed by the run itself;
the replay only fills the *other* years, so widening the grid cannot move the
year anybody is looking at. Backend suite: 744 passed with the parity gate.

**Cost:** 6 month rows became 36 per client. Not measured as a response-time
delta, because the read query was unchanged — the same single statement now
joins rows that exist. Row counts on the client page did not regress.

---

## Round 1 — the fold

At 1024×768 via `frontend/tools/measure_ui.py`, counting rows whose **bottom
edge** is inside the viewport, not rows that merely exist.

| Page | Required | Measured | Result |
| --- | --- | --- | --- |
| `/` | all 5 client rows | **5** visible of 6 | pass |
| `/c/2001?year=2023` | ≥ 12 data rows | **12** visible of 37 | pass |
| `/c/2001/u/GA_GA-010…` | ≥ 10 employee rows | **11** visible of 33 | pass |

The portfolio's sixth row is the totals row; all five clients are visible.

### Diagnostics

| | Before (`7cae036`) | After (`191bcee`) |
| --- | --- | --- |
| content width, all pages | 828px | **1024px** |
| first data row — portfolio | 806 → 524 | **491** |
| first data row — client | 1641 → 1375 | **330** |
| first data row — unit | 714 → 496 | **457** |
| rendered row height | 53 / 43 | **28** (40 on the portfolio matrix) |
| client page scroll height | 2466px | 2949px |

The client page's scroll height went **up**, and that is the intended trade: the
grid is now expanded by default, so 37 rows are present where 1 was. More total
scroll, but the first twelve are free.

The portfolio matrix renders at 40px rather than 28 because each cell holds a
two-line button (amount over label). Compressing it to 28 would mean dropping
the label, which changes what the cell says. Left at 40; the gate passes.

### Other gates

- `npm run build` — passes, 13.76s.
- `npm test` — **309 passed, 7 failed** of 316. Detail below.
- `git diff backend/` — empty. Frontend only.
- Evidence, Compare and Methodology unchanged: they call the no-argument
  workspace endpoints and the ⋯ menu passes no client, so the sealed property
  holds structurally.

---

## What changed

### Fix 1 — the missing 196px

`.tcc-main { margin-left: 196px }` survived in the desktop media query after
the sidebar element was deleted. `1024 − 828 = 196` exactly, as the brief said.
Removed, along with the now-dead `.tcc-sidenav` rules in both breakpoints and
the `tour-bar` offset that assumed a nav to sit beside.

Doing this first was right: it changed what everything else had to fit into.

### Fix 2 — the vertical stack

- **Heading stack collapsed.** The eyebrow, the page subtitle and the in-page
  method selector are gone. The method selector was the same control twice —
  `TopScope` in the top strip already owns it.
- **Five KPI cards → one line of figures.** `6 locations · 5 qualify · $607,110
  claimable · …` — same numbers, ~32px instead of ~120px.
- **Two banners folded into the answer band** as a single `answer-note`. The
  base-year caveat and the declined-years list are conditions on a figure, not
  page-level announcements.
- **The answer band stays**, tightened from 14/18px padding and margin to 7/6.

### Fix 3 — density

28px rows, 24px sticky uppercase headers, 8px cell padding, `tabular-nums`
right-aligned numerics, hairline separators only. The client grid is expanded
by default — previously it opened only units with `attention` or clients with
≤4 units, so Cascade's six units all rendered collapsed and the page showed
**one** row. Its length is the point.

The month-12 zeros and the hatched unreachable months are untouched.

---

## The seven failing tests — still red, and why

`npm test` is **323 passed, 7 failed of 330** (14 new `gridSort` tests were
added). The seven are the same seven as the first run.

I did break seven more this round and fixed them: `TrendGridView` now uses
`useSearchParams`, so tests rendering it standalone hit
`useLocation() may be used only in the context of a <Router>`. Wrapping those
renders in `MemoryRouter` is a harness change and touched no assertion. Count
went 7 → 14 → 7.

The original seven all drive the client through `whoSelect()`, the scope bar's
"Who" combobox, which this work deletes. They **can** be rewritten — mount at
`/c/2001` through `MemoryRouter`, which is the new mechanism and what several of
them already assert. Clicking a client in the portfolio matrix is not available
to this suite, because it mocks `fetchPortfolioCoverage` with `clients: []`.

They were not rewritten again this round. Each round has ended with the same
honest constraint: room to change them but not to verify them, and the brief is
explicit that an assertion must not be loosened to make something pass.

| Test | What it guards |
| --- | --- |
| keeps the selected client when moving between views | scope is a session property |
| restores the scope on reload | persistence |
| asks for the newly selected client | the view re-reads on scope change |
| drilling from the portfolio matrix sets scope, not just the view | drill sets both |
| uses the route and query string as the source of truth | the URL is the scope |
| falls back to the stored scope only when the URL omits client and year | precedence |
| still mounts and says what went wrong | a broken `/api/scope` degrades honestly |

---

## Changed meaning rather than appearance

Six things, all deliberate:

1. **The client selector is gone from the chrome.** The client is set by the
   URL. This is what the brief asked for and it is why the seven tests fail.
2. **The year selector does not render on the client page.** It still exists in
   the URL and on the other three pages.
3. **Method is no longer global.** It is set on the client grid, and on the unit
   page only via the URL — see the gap above.
4. **The grid expands by default.** Previously it collapsed all but units
   needing attention. An operator at a twenty-location client now scrolls past
   twenty open grids rather than hunting for the problem — the brief chose this,
   and the trade should be re-examined for a large client.
5. **The in-page method selector was removed and then re-added** as a tab group.
   Any muscle memory for the old dropdown is gone.
6. **`unit_month_summary` now holds every replayed year.** More rows per run,
   and Cascade's stored run was replaced by the backfill.

No figure, calculation, or copy stating a number was altered.

## Still not done

- ⌘K is not re-scoped to pass `client_id`/`tax_year`/`method` per page.
- Evidence/Compare/Rules/Methodology are in the ⋯ menu but not reachable from
  the provenance line, which the brief calls the more important half.
- Breadcrumb and page actions are not on one line.
- 1440×900 was never measured; the gate specified 1024×768.
- Phase 9 (brand — Roboto, purple/magenta, hex retirement) not started.
  `--radius` exists as the single squircle approximation, documented as one.

---

# The root URL landed on the last client

Reported live: opening the app went to Cascade rather than the portfolio.

## What it was

`parseRouteState` returned `clientId: null` for `/`, and the scope effect read

```js
clientId: routeClientId ?? current.clientId ?? fallback.clientId,
```

so `/` fell through to the client saved in `localStorage`. The view branch keys
on `resolved.scope.clientId`, not on the URL, so `ClientPage` rendered while the
address bar still said `/`. Nothing syncs scope back to the URL, so the two
disagreed until the next explicit navigation.

## The conflict this exposed

Two documented rules pointed opposite ways, and a passing test encoded the
losing one:

| Rule | Where |
| --- | --- |
| ``/` is PortfolioPage, the book`; a pasted URL renders that state cold | `.github/copilot-instructions.md` |
| A stored client scope lands on that client's page, not the portfolio one | `App.test.jsx`, in a comment |

The URL rule wins: `/` is not "the URL omits the client", it positively means
the book. This is a **behaviour decision**, not a test that was in the way.

## What changed

- `parseRouteState` now reports `isRoot`.
- At the root the client resolves to `PORTFOLIO` and ignores storage. Every
  other path is untouched, so `/position` still restores the stored client —
  which is what `falls back to the stored scope only when the URL omits the
  client and year` actually asserts.
- `persists the RESOLVED scope, not the requested one` used the old landing as
  scaffolding for a check about the **year**. It now mounts at `/c/1001`; the
  year assertion is unchanged, and no expected value was touched.
- New test: `shows the book at / even when a client was stored last time`.

## Gate

| | Before | After |
| --- | --- | --- |
| `/` after opening Cascade (live Playwright, 1024×768) | `Position by location` | `The book` |
| Reload at `/` | `Position by location` | `The book` |
| Frontend suite | 323 passed, 7 failed | 324 passed, 7 failed |

The 7 are the pre-existing failures that drive the deleted `whoSelect()`
combobox. None is new.

## Left open

`restores the scope on reload` remounts at `/` and expects client 2001, so it
now asserts the behaviour this change deliberately removed. It is already red
for the combobox, so it is not masking anything — but when the seven are
rewritten it needs a decision, not a mechanical port. The session continuity it
protects is real; the client axis is just no longer the part that carries it.

---

# The unit card becomes a grid row

## What the card cost

`.trend-block-head` held four stacked things per location — name, meta, the
narrative sentence, and the tranche chips. Roughly 400px before the first data
row, repeated per unit. Cascade has six locations; a twenty-location client
spent its whole viewport on chrome.

It is now a single row: name, unit id, FEIN, tier, net-new, credit, and the
reading. Weight and a hairline rule separate it, not a card.

## Two things survived, and one nearly did not

The tranche chips and `block.sentence` moved into an expand on the row. The
chips keep `opacity: .55` and `border-style: dashed`, measured live:

| | opacity | border |
| --- | --- | --- |
| measured installment | 1 | solid |
| projected | 0.55 | dashed |

**The first cut made the client page WORSE, not better** — first data row moved
330px to 371px and visible rows fell from 12 to 9. Units are expanded by
default, so putting the detail inside that same expand added its height above
every table. Splitting it into its own toggle is what actually reclaimed the
space: the years table no longer costs the tranche stream.

## A base year is not a below-minimum year

Colour encodes state and nothing else. Measured from the rendered pills:

| row | pill background | ink |
| --- | --- | --- |
| Base year | `rgb(238, 243, 251)` | `rgb(38, 71, 141)` |
| Below minimum | `rgb(253, 232, 222)` | `rgb(194, 65, 12)` |

Net-new renders `—` in a base year rather than a red zero. One means we hold no
prior year; the other means they did not grow.

## Server-side sort and filter

`GET /api/v2/clients/{id}/units/{unit_id}` gained `sort`, `order`,
`near_min_hours` and `limit`. The response shape is unchanged.

```sql
SELECT TOP 5 m.employee_id, ... FROM tcc_gold.onezero_matrix AS m
LEFT JOIN tcc_gold.employee_eligibility AS e ON ...
WHERE m.client_id = ? AND m.worksite_id = ? AND m.tax_year = ?
  AND m.method = ? AND m.run_id = ?
ORDER BY e.avg_weekly_hours DESC, m.employee_id
```

Live against client 1001, unit `GA_1134481`, TY2023:

| request | rows | first values |
| --- | --- | --- |
| `sort=avg_weekly_hours&order=desc&limit=5` | 5 | 47.9, 45.4, 39.9, 35.5, 35.5 |
| `sort=avg_weekly_hours&order=asc&limit=5` | 5 | 35.1, 35.4, 35.5, 35.5, 35.5 |
| `sort=avg_weekly_wages&order=desc&limit=5` | 5 | 2196, 1366, 1340, 1268, 1123 |
| `sort=employee_id&order=asc&limit=5` | 5 | 16757852, 16769265, 16773749, … |

The near-threshold band narrows 206 rows to 19 within five hours of the floor,
and 7 within two.

**The band arrives as an absolute hours figure**, not as a band. The caller
subtracts what it considers close from the statutory minimum the same response
already returns in `thresholds`. A literal 35 in the query would make Georgia's
floor everyone's, which is the rule this codebase already states for the page.

`sort=employee_id` returned a 500 on the first live attempt: the stable tiebreak
duplicated the sort column, and SQL Server rejects a column named twice in one
`ORDER BY`. Caught against Fabric, not in the unit tests, which is why the fix
carries one.

## Method on the unit page

`MethodTabs` is now one component used by both the client grid and the unit
page. On the unit page it writes the URL rather than local state, so the reading
survives a paste. Measured: one tab group on the unit page, zero in the top
strip, and clicking Pay Period moves the URL from `method=min_max` to
`method=pay_period`.

## Gate, at 1024×768

| page | visible | total | 1st row y | before |
| --- | --- | --- | --- | --- |
| portfolio | 5 of 5 | 6 | 467 | 5 / 467 |
| client | 12 | 37 | **306** | 12 / 330 |
| unit | 11 | 33 | 457 | 0 rows |

Client page scroll height 2949 → 2746.

| | |
| --- | --- |
| Backend | 792 passed, 66 skipped, 1 xfailed |
| Frontend | 336 passed, 7 failed — the same pre-existing 7 |
| `npm run build` | passes |
| `git diff backend/domain/calculation/` | empty |
| Backend change | `trend.py` params + `gold_reader.py` statements only |

## Found on the way, not fixed

The unit drill resolves its run with `AND tax_year = ?`, but a run now writes
every year into Gold. Client 2001's live run was TY2025, so
`/c/2001/u/...?year=2023` reported `not_calculated` while Gold held the rows —
the measurement harness read 0 rows for the unit page. Re-running 2001 at TY2023
restored it, which is a data action, not a fix: the manifest's `tax_year` is the
year the run was COMMANDED for, not the only year it produced, and filtering on
it makes five years of six unreachable in the drill. The prompt limited backend
changes to the sort and filter parameters, so this is recorded rather than
changed.

---

# Brand

Nothing that says something changed. The only non-CSS source edit is five
import lines in `main.jsx`; no component file was touched, so no figure, label
or sentence could have moved.

## Roboto, self-hosted

`@fontsource/roboto`, latin subset, the five weights the stylesheet actually
asks for (400, 500, 600, 700, 800) — counted from the file rather than guessed.
Bundled, never hotlinked: a demo on a network that cannot reach
`fonts.gstatic.com` would silently fall back to Segoe UI, which is the exact
failure being replaced.

Roboto had been present all along as the FIFTH entry in the Tailwind stack,
behind Inter and Segoe UI, so it never won. It now leads, and `--font-sans` is
one token both declarations read.

Computed on the rendered page, not read off the declaration:

```
body     Roboto, -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif
heading  Roboto, ...
cell     Roboto, ...
document.fonts.check('12px Roboto') -> true
```

`Segoe UI` appears nowhere in any computed value. Ten font files ship in
`dist/assets` (woff2 + woff per weight, ~21KB each); zero requests to
`fonts.googleapis.com` or `fonts.gstatic.com`.

## The fold survived the swap

Roboto's metrics differ from Segoe UI, so this was measured after, not before.
No line-height adjustment was needed.

| page | visible | total | 1st row y | before |
| --- | --- | --- | --- | --- |
| portfolio | 5 of 5 | 6 | 467 | 5 / 467 |
| client | 12 | 37 | **298** | 12 / 306 |
| unit | 11 | 33 | 457 | 11 / 457 |

The client page gained 8px rather than losing rows.

## Colour still means something

The two readings that colour carries are unchanged to the byte:

| row | background | ink |
| --- | --- | --- |
| Base year | `rgb(238, 243, 251)` | `rgb(38, 71, 141)` |
| Below minimum | `rgb(253, 232, 222)` | `rgb(194, 65, 12)` |

They are tokenised as `--state-base-year` and `--state-below-min`, named for
what they MEAN. A base year is "we hold no prior year to measure against";
below minimum is "they did not grow enough". A name like `--blue-100` would
have invited the next person to reuse it somewhere it means nothing, and the
two swatches sit close enough that only the name keeps them apart.

The state tokens ALIAS the existing values rather than restating them, so the
computed colours provably could not drift during the migration. A first pass
gave `--state-partial` a fresh literal and silently moved the caution tint;
aliasing is what caught it.

Projected tranche chips remain `opacity: 0.55` and `dashed` against a solid,
fully opaque measured one.

## Purple, used rather than reserved

`--exp-purple` and `--exp-violet` were defined and essentially unused, under a
comment asserting they were "brand chrome only". The guide says the warm
purple, raspberry and magenta tones "should be used generously".

Purple now carries CHROME selection — active nav entry, active tab, drill tab,
overflow-menu entry, focus ring. Blue stays the core thread on everything that
encodes a reading, so a selected tab can never be mistaken for a statutory
verdict. Purple appears in 18 places, up from effectively zero; magenta 10.

## Literals

| | before | after |
| --- | --- | --- |
| hex in the file | 152 | 47 |
| hex OUTSIDE `:root` | 126 | **6** |

118 literals were mapped onto tokens — four near-identical page tints onto
`--surface-2`/`--surface-3`/`--surface-4`, two greens onto
`--state-above-min-ink`, two oranges onto `--state-below-min-ink`, and the
purple family onto `--accent-2-*`.

The six survivors are all inside `@media print` and carry a comment saying why:
print wants true black and a neutral rule on white paper, not the screen
palette. Tokenising them would tie the printed evidence pack to a theme it is
never rendered under.

## Gate

| | |
| --- | --- |
| `npm test` | **343 passed, 0 failed** |
| `npm run build` | passes |
| `git diff backend/` | empty |
| Google font requests at runtime | none |

---

# The design system

The brand pass fixed the palette and the font. It never established a SCALE,
and it never went view by view. Nothing that says something changed: no figure,
label or number-bearing sentence was touched.

## There was no type scale

23 sizes across 321 uses, **105 of them half-pixel**. Nobody designs a 10.5px
step; each one is a person nudging one screen until it looked right.

Eight tokens, named for the job — `--text-micro` through `--text-display`. Each
step is the size that was ALREADY most used in its band, so the migration
mostly shrinks or holds; only `8/8.5 -> 9` and `17 -> 18` grow, across nine
declarations. That choice is why the fold improved rather than survived.

| | before | after |
| --- | --- | --- |
| distinct raw font sizes | 23 | **0** |
| half-pixel uses | 105 | **0** |

## The spacing tokens were ignored because they were unhittable

`--space-1..5` covered 6/10/16/24/34 and were used **eleven times** against 381
raw declarations. The values people actually needed — 2, 4, 8, 12, 14 — were
not on the scale. A scale nobody can hit is a scale nobody uses.

Ten steps now: 2px increments to 16, then 20 and 24. Odd values round DOWN,
because rounding up costs rows and the fold is gated. `gap` was migrated with
them: leaving it raw while padding was tokenised is the half-migration that
makes neither the tokens nor the literals trustworthy.

| | before | after |
| --- | --- | --- |
| raw px in padding/margin | 381 | **0** |
| raw px in gap | 190 | 0 |
| distinct border-radius | 17 | **5 tokens** + `50%` and `0` |

Three values refused the scale and got named instead. `--topbar-offset` is the
fixed header's height, which the main column must clear — it tracks the header,
not the scale. Two left indents became `calc(var(--space-8) + var(--space-6))`,
which says "icon plus gap" rather than an invented 28.

**The measurement had a blind spot.** The first metric skipped any declaration
containing `var()`, so `padding: 58px var(--space-9) 40px` counted as clean.
Eleven raw values were hiding behind a partial migration. The metric now counts
raw numbers, not raw declarations.

## Inline styles

29 to 2. The two survivors carry comments and are honest:

- the tour progress bar's width is COMPUTED per render; no class carries a
  percentage that changes every frame.
- `react-simple-maps` takes `style` as a library **prop** — default/hover/
  pressed objects — which no class can express.

The map was worth more than its two inline styles, though: it encoded a READING
in hardcoded hex, and the legend repeated those hexes by hand. Map and legend
now both read `--map-*`, so they cannot drift apart about what "priced" looks
like.

## The view inventory

| view | shared components used | hand-rolls | note |
| --- | --- | --- | --- |
| UnitPage | PageHeader, StatCard, Breadcrumb, MethodTabs, AnswerBand | — | the reference composition |
| PositionView | PageHeader, StatCard | — | |
| TrendGridView | MethodTabs, AnswerBand | — | its unit rows are a grid, not cards |
| ClientPage | Breadcrumb | — | composes PositionView and TrendGridView |
| EmployeePage | Breadcrumb | — | |
| PortfolioPage | AnswerBand | — | |
| EvidenceView | PageHeader | — | **adopted this round** |
| ProvenanceView | PageHeader | — | **adopted this round** |
| RuleLibraryView | PageHeader | own stat block | KPI strip, not converted |
| EligibilityView | PageHeader | own stat block | in `ReferenceViews.jsx` |
| OneZeroView | PageHeader | own stat block | in `ReferenceViews.jsx` |
| CompareView | PageHeader | — | in `ReferenceViews.jsx` |
| AssumptionsView | PageHeader | — | in `ReferenceViews.jsx` |
| CalculationWalkView | PageHeader | — | embeddable |
| DataIngestionView | — | own stat block | a work queue, no answer band |
| AgentActivityView | — | own stat block | a work queue |
| PlanView | — | — | split by export; no header of its own |
| ProgressView | — | — | rendered as a SECTION of ClientPage |
| ProximityView | — | — | rendered inside ProgressView |

**The finding worth carrying forward:** `ReferenceViews.jsx` defined its OWN
`PageHeader` — different prop name (`subtitle`), different classes
(`.page-header .tcc-page-header` against `.tcc-header`) — and **eight call
sites across four files used it**. Two header treatments kept in step by hand.
The duplicate is gone and the file re-exports the shared one, so its three
sibling importers did not have to move. `.tcc-header-actions` joined the print
hide-list, which `.top-actions-local` had been doing alone.

`ProgressView`, `ProximityView` and `PlanView` render no header because they
are SECTIONS, not destinations — that is composition working, not a gap. The
four "own stat block" views use `kpi-strip`, which `StatCard` does not express:
StatCard is a labelled figure, the KPI strip is a clickable four-across summary.
Bending one into the other would be worse than the honest duplicate, so they
are reported and left.

## Gate

| | before | after |
| --- | --- | --- |
| portfolio visible rows | 5 of 5 | **5 of 5**, first row 467 -> 459 |
| client visible rows | 12 | **13**, first row 298 -> 294 |
| unit visible rows | 11 | **11**, first row 457 -> 450 |

Base year `rgb(238,243,251)` / `rgb(38,71,141)`; below minimum
`rgb(253,232,222)` / `rgb(194,65,12)` — unchanged to the byte. Chips still
`0.55`/dashed against solid. Roboto still computed; no Google requests.

`npm test` 343 passed, 0 failed. `npm run build` passes.
`git diff backend/` empty.

---

# The type floor

The scales landed in `3fd8b21`. This round is the part the Carbon reference
added: a floor for text a reader reads AS DATA.

## What Carbon actually says, and where we diverge

IBM Carbon's data-table spec puts row text at **14px** and column padding at
**16px**, with row heights xs 24 / sm 32 / md 40.

| | Carbon | here | deliberate? |
| --- | --- | --- | --- |
| row height | 24 / 32 / 40 | **28** | YES — measured for an operator who thinks in spreadsheets |
| column padding | 16px | **8px** | YES — 17 columns in a 1024px viewport |
| row text | 14px | 11px | **NO** — nothing chose it |

The row height and the column rhythm are real divergences with a measured
reason behind them. The type was not: 45 uses at 11px, 41 at 11.5px, 24 at
10px, 18 at 9px is what is left when nobody owns the scale.

## The floor

12px for anything read as data — table cells, headers, figures, verbatim engine
output. Chrome is not data: an eyebrow, a chip caption, a pill, a sort-rank
superscript may go smaller.

| | before | after |
| --- | --- | --- |
| smallest RENDERED text in a data table | 10.0px | **12.0px** |

Measured on the rendered page rather than from the stylesheet. A selector audit
over-reports badly — it flags `.th-sort sup` as a table header and
`.tour-step-num` as a figure — so `check_type_floor.py` reads computed sizes off
live cells instead. That distinction is why the number is trustworthy.

## The density was being bought with legibility

Raising `.tcc-cell-btn` — the trend grid's month cell — from 10px to 12px cost
a row: the client page dropped 13 to 12 and the row height went 28 to 29.

`line-height: 1` bought the 28px row back AT 12px. The cell was paying for a
line-box problem with type size, which is exactly the failure the half-pixel
rule describes. Worth knowing before anyone reaches for a smaller font to win
a row.

## A selector defined twice

`.tbl-compact th, td` was declared in TWO places 1100 lines apart:

```
line  436   padding: var(--space-2) var(--space-4);  font-size: var(--text-body)
line 1590   padding: var(--space-2) var(--space-3);  font-size: var(--text-small)
```

The later one won silently, so the trend grid rendered at 11px while the file
looked like it said 12px. Collapsed to one rule at the floor with the 8px
column rhythm.

## Carbon's 16px column rhythm was tested, not assumed

Trialled on the trend grid and measured: the table is width-constrained, so it
absorbs the extra padding by shrinking columns rather than overflowing — it
reports as "fitting" right up until the figures are unreadable. At 16px the
narrowest cell falls to 39px; at 8px it is 41px. Nothing clipped either way,
but the margin is thin enough that 8px stays, and `check_cell_fit.py` now
guards it.

## Gate

| page | visible | 1st row y | before this round |
| --- | --- | --- | --- |
| portfolio | 5 of 5 | 482 | 5 / 459 |
| client | **13** | 294 | 13 / 294 |
| unit | 11 | 453 | 11 / 450 |

Trend cells: 678, **0 clipped**, narrowest 41px.
Base year `rgb(238,243,251)`/`rgb(38,71,141)`; below minimum
`rgb(253,232,222)`/`rgb(194,65,12)` — unchanged. Chips `0.55`/dashed. Roboto
computed; no Google requests.

`npm test` 343 passed, 0 failed. `npm run build` passes.
`git diff backend/` empty.

Font sizes 0 raw / 0 half-pixel, raw padding-margin 0, inline styles 2 — all
unchanged from `3fd8b21`, verified rather than assumed.

---

# Tabs, columns, and filters

## Two stacked grids became two tabs

Both pages showed a second grid a screen below the first, so the second label
was invisible until you scrolled to it.

| page | tabs | opens on | why that one |
| --- | --- | --- | --- |
| `/` | **The book** (5) · **Who to call** (1) | The book | The complete population, and the page's stated job. Who to call is a ranked SUBSET of it, and opening on a subset makes the book the thing you have to find |
| `/c/:id/u/:unit` | **Counted** (26) · **Near the floor** (217) | Counted | What the page title claims to show and what the credit is computed from. Near the floor is a lead derived from it; defaulting to a lead list buries the statutory answer |

Every label carries its count, so the tab says whether to click it. "Near the
floor (0)" saves the click entirely.

**The shape is `MethodTabs`, deliberately** — a third tab style makes "which of
these is a tab" something a reader has to work out. The ACCENT differs because
the job does: MethodTabs picks a statutory reading, which is blue; this picks
which population is on screen, which is chrome selection and therefore purple.
That is the existing rule applied, not a new one.

## The answer band points at the hidden tab

The portfolio opens with *"Ironbridge Logistics is 0.8 jobs from qualifying"*
and the evidence is in the second grid. Tabbing a claim away from its support
is worse than the scroll it replaced, so the client name is a control:

```
/                     ->  click "Show Ironbridge Logistics in Who to call"
/?ptab=call&focus=2003 -> tab switches, row scrolls into view and is marked
```

Verified end to end: selected tab `Who to call`, `.row-focus` contains
`Ironbridge Logistics GA_JTC TY2022 1.17 2 0.83`.

## The unit grid earns five more columns

Four columns of mostly whitespace became eight. Each one had to answer
something no other column answers:

| column | what it is for |
| --- | --- |
| **Weeks** | The denominator behind the weekly average. 40 hrs/wk over 6 weeks and over 52 render IDENTICALLY without it, and they are different facts |
| **Worked** | WHERE in the year those weeks fell. Six weeks in January and six weeks spread across the year have the same average |
| **Total hrs** | The numerator. With Weeks beside it the average is auditable from the row |
| **Short by** | Already there on the near list; now both tables share the rest of the shape |
| **Share** | The fraction of an employee allocated to this location. **Rendered only when it varies** — it is 1.00 for almost everybody, and a column reading 1.00 on every row costs the same width as one that says something. Same rule the client grid already applies to tier |

Deliberately NOT added: `days` (weeks says it better), `total_wages` (the wage
average already carries it), `eligible` (constant within each tab — it is what
the tabs are), `record_token` (it is the link).

`weeks_worked` is FRACTIONAL in the warehouse — 50.86, not 51 — so it renders to
one decimal. Rounding to whole weeks would present a derived figure as a count.

**Which rows appear did not change.** Verified against the live run:

```
run_id      9ef20a4be10e4350967271c3829dae2b
employees   10236        min_max  539        pay_period  656
```

## One filter grammar, two places it runs

`frontend/src/lib/gridFilter.js` and `backend/tools/grid_filter.py` agree on one
wire form. Writing it twice is how a control ends up meaning one thing on screen
and another in the query.

```
col:expr;col:expr

text     employee_id:~ABC            contains, case-insensitive
numeric  avg_weekly_hours:>=35       comparator
         weeks_worked:10..52         inclusive range
enum     status:qualified|declined   multi-select
year     tax_year:2023|2024          multi-select
```

**Where the work happens is a function of row count, not house style:**

| grid | rows | filtered |
| --- | --- | --- |
| portfolio matrix | 5 clients | browser |
| client grid | 36 location-years | browser |
| unit grid | up to 10,236 employees | **SQL** |

### Server-side, demonstrated

```sql
SELECT m.employee_id, ..., e.weeks_worked, e.total_hours, e.first_start, e.last_end
FROM tcc_gold.onezero_matrix AS m
LEFT JOIN tcc_gold.employee_eligibility AS e ON ...
WHERE m.client_id = ? AND m.worksite_id = ? AND m.tax_year = ?
  AND m.method = ? AND m.run_id = ?
  AND (e.avg_weekly_hours >= ?) AND (e.weeks_worked >= ?)
ORDER BY e.avg_weekly_hours DESC, m.employee_id
```

```
GET /api/v2/clients/1001/units/GA_1134860?...&filter=avg_weekly_hours:>=35;weeks_worked:>=26
    -> 21 of 26, 344ms
```

The predicate is IN the WHERE. A test that fetched rows and counted them would
pass just as well if the narrowing happened in Python, so the tests read the
statement text instead.

**The column name is never interpolated unless it matched a whitelist**, and
every value is bound. `1=1 OR x:>=1;DROP TABLE t:~a` compiles to the empty
string. LIKE wildcards in a needle are escaped, or a filter could widen itself
while the chip still claims to be narrowing.

### One of each type, driven through the UI

```
ENUM     Reading: below minimum          Showing 4 of 36 location-years
         offered ['above minimum','base','below minimum'] -- from the data
YEAR     + Tax year: TY2023              Showing 1 of 36 location-years
NUMERIC  avg_weekly_hours>=35, weeks>=26 Showing 21 of 26 employees   (SQL)
TEXT     employee_id ~6480               Showing 1 of 26 employees     (SQL)
TEXT     Client contains "candle"        Showing 1 of 5 clients
```

An enum offers the values PRESENT in the data. A hardcoded list goes stale the
first time a status is renamed and then offers a filter matching nothing, which
reads as "no rows" rather than "no such value".

### An unparseable term is dropped, not widened

```
?emp_f=weeks_worked:banana
  -> request carries NO filter param
  -> nothing on screen claims to be filtering
  -> 26 rows
```

A predicate that silently matches everything is worse than no filter: the page
says it is filtering and the total says otherwise. Dropped at parse, so it can
never appear as an active chip.

### A filtered grid states what it is hiding

`Showing 12 of 37`, a removable chip per filter, and Clear all. The denominator
comes from a COUNT carrying the same predicates minus the filter — issued inside
the batch already being sent, and only when a filter is in force.

**A filter narrows the LIST, never the location's answer.** The tab count, the
stat cards and the answer band all read the unfiltered total. Where that is not
possible — the within-band cusp count, which is derived from the near rows
themselves — the figure is WITHHELD and says why, because a filtered cusp count
is a different figure wearing the same words.

### The two cohorts filter independently

`filter` and `near_filter` are separate params. They are different questions
about different populations, and one shared control would let a narrowing of the
counted list move the near-miss count under a tab nobody is looking at.

## What was NOT reached

`/api/v2/portfolio` briefly gained a `client_q` text filter with no grid behind
it. **It has since been removed** — the portfolio page renders the coverage
matrix (`/api/claims/coverage`, client x program), not the v2 list, so the
param was API surface nobody called. The list's existing
`outcome`/`scope`/`near`/`status`/`year`/`program` filters remain unwired to any
header for the same reason. The matrix's own Client filter is client-side over
five rows, which is the right call for five rows.

Outcome is deliberately NOT a matrix filter. A cell already carries its outcome
as a colour and a word, and hiding the exposures is the one thing that view
exists not to do.

## Gate

| page | 1024x768 | 1440x900 | required |
| --- | --- | --- | --- |
| portfolio | **5 of 5** | 5 of 5 | all 5 client rows |
| client | **13** | 18 | >= 12 |
| unit | **11** | 16 | >= 10 |

Rows 28px on both grids. Smallest rendered data text 12.0px. Trend cells 678,
**0 clipped**; narrowest 41px -> 38px, because four headers gained a filter
icon. Still clear, and `check_cell_fit.py` now guards it at that margin.

`npm test` 384 passed / 0 failed (was 343; the added tests are the tabs, the
columns, the grammar and the SQL). `npm run build` passes.
Backend 821 passed; the 3 `test_warehouse_adapter` failures are a missing local
`pyodbc` and fail identically on a clean checkout of `c6301d5`.
`git diff backend/domain/calculation/` EMPTY.

---

# The partner's §2 — sorting, decline, the map, and Sally

Run date: 17 September 2026, on `main` from `8935a3a`. The acceptance criteria
are the partner's demo outline for 1 October, not a preference.

**Outcome: four of the five items are done and verified against live Fabric.
The fifth — the legal-entity drill level — is NOT done and is inventoried
below.** Three defects were found by looking at the rendered page rather than
by a test, and all three are fixed; one of them was live before this work and
had been on screen for weeks.

## Sort headers on the book

The partner: *"Sort clients by estimated credit amount and focus resources where the
greatest financial impact exists."*

`SortHeader` was lifted out of `TrendGridView` into its own file and imported
back. It is the same component in both places, which is the point — a second
implementation is how a click comes to mean one thing on one grid and something
else on another.

The two grids do NOT share a grammar, and should not:

| | Rows | Where it sorts | Keys |
| --- | --- | --- | --- |
| trend grid | 36 | browser, `gridSort.js` | multi, shift-click |
| the book | whole portfolio | **the endpoint**, `bookSort.js` | one |

So `SortHeader` takes `multi={false}` for the book and hides the shift-click
affordance. Offering a second key the server will ignore is worse than not
offering one. The URL param is `bsort`, deliberately not `sort` — the trend grid
owns `sort` and parses it against its own columns, and one name for two
grammars is how a shared URL renders one page right and the other silently
unsorted.

**The default is still the band ranking, and choosing dollars is visibly a
choice.** `ranksByValue()` drives an amber callout above the grid — *"Ranked by
value, not by band. That buries a client one hire from a threshold — they are
worth $0 today, the same $0 as one fifty hires short"* — with a button back. The
closing note switches too, and the answer band stops claiming a *"top of the
call list"* it no longer has: under a value sort `rows[0]` is the biggest
number, not the next call.

`program` gets no sort header. `_portfolio_sort_key` has no alias for it, and a
header that looks sortable and does nothing is worse than a plain one.

## At risk — a sixth band, and it is not exposure

The partner: *"Clients whose employment levels are trending downward · Companies at
risk of losing credits."*

`PriorityBand.DECLINING`, rank 2, **above** `unclaimed_at_scale`: money you are
about to lose outranks money you have not collected.

**It is not `EXPOSED`, and it does not render like it.** Exposure is a finding
against a return somebody has already filed. This is a forecast about a year
nobody has filed yet. `exposed` (rank 0) and `on_the_line` (rank 1) both still
outrank it and neither can be displaced by it, so a client that is both says the
thing that has already happened. Visually the chip is the only one drawn as a
dashed OUTLINE rather than a fill — same urgency, visibly not the same kind of
statement. `test_declining_is_not_exposure` and a frontend test pin both halves.

It is also not the per-employee `at_risk` read. `gold_reader.at_risk()` and
`chat_jobs_at_risk()` are unit-grain and untouched.

**A trend is not a cell**, so no `ProgramClaim` can carry it. `declining_reading()`
takes the client's whole history and the overlay applies it over the cell band.
It returns `None` rather than `declining: false` — an absent trend and a flat one
are different, and only one earns a band. It also requires that the client
actually EARNED credit at the higher level: shrinking is only a credit problem
if there is a credit to shrink out of.

**Halloway Foods is the live case, and it was banding as `settled`** —
*"Nothing outstanding"* — on a client that has shed 39.33 jobs since TY2022 and
is now below the base year it earned $208,845 from. It now ranks **first** in
the book. Northwind dipped in TY2022 and has climbed since, and is correctly
excluded: the reading is about where a client is heading now.

The row line is `↓ 39.3 jobs since TY2022`, with the full sentence and *"Now
below the base year the credit was earned from"* as its title. The headline
figure is the credit ALREADY EARNED, not this year's `identified` — which is
`—` for Halloway and would read as an opportunity.

### The defect this nearly shipped with

The first cut read the trend from `grouped`, which is the claims left after the
`year` filter. **Every real page load is year-scoped** — the shell sends
`year=2025` — so that is one year per client, and one year has no direction.
Halloway read `declining` only on the unscoped call nobody makes, and `settled`
on the screen. Found by opening the page, not by a test. `history` is now read
from the full set and `test_the_trend_survives_the_year_filter` pins it.

## The map moved to the book, as a filter

`FootprintMap` was explicitly excluded at portfolio scope in `PositionView`. It
now renders on the book and drives `gridFilter.js` — **not a parallel
mechanism**. Clicking a state toggles it in the shared `state:` expression, so a
chip cleared in the filter bar clears the map too.

That needed one small widening of the grammar, expressed as a property of the
COLUMN rather than as a new operator: a cell may hold several values, and then
the row matches if any of them is selected. The written form stays `col:a|b`
everywhere, so `tools/grid_filter.py` is unchanged.

Backend, per the brief, on the existing response rather than a new endpoint:
`states` and `priceable_states` per row, from one `GROUP BY AccountId, state`
over Payroll — not one `payroll_scope` call per client. Unassessed clients carry
it too; where a client operates is a fact about payroll, not about having run
it, and dropping it there would take exactly those clients off the map.

Live, and it matches `synth.py`:

| Client | Holds payroll | Priceable |
| --- | --- | --- |
| Cascade | GA, NC, SC | GA |
| Northwind | GA, TN | GA |
| Ironbridge | GA | GA |
| Halloway | GA, SC | GA |
| Candle Bottle | GA | GA |

Only GA has year-scoped packs, so NC, SC and TN are held-but-unpriceable and
render in the second shade with *"no authored statute"* on hover. That is a real
gap in statutory coverage and the map is the one screen that shows it.
Selection is drawn as a purple OUTLINE, never a fill — filling it would
overwrite the priced/held distinction the map exists for.

## The Sally question

The partner: *"How many additional hours per week would Sally need to work?"*

`assess_employee` is CALLED, not copied — `git diff backend/domain/calculation/`
is empty. `_with_lever` attaches `additional_weekly_hours`,
`projected_weekly_hours`, `exceeds_plausible_week`, `failure_mode` and
`hourly_rate_to_qualify` to the near-threshold cohort.

**No per-person dollar figure.** A location's credit turns on its job count
against a threshold, so the marginal employee is worth the whole tranche if they
cross it and nothing at all if they do not, and there is no honest way to
attribute that to a row. Per the brief: say the hours, not the dollars. The one
money field is a RATE — what to pay them — not a credit value, and
`test_the_lever_never_reports_a_dollar_value_per_employee` pins the field set.

### Two defects the screen showed and the tests did not

**The `$` marker was money.** The wage-bound superscript was a literal dollar
sign in a numeric column, which reads as a figure however it is marked up. It is
`†` now — and my own test caught it.

**"Short by" was reporting a negative shortfall, and still is on `main`.** The
near cohort is everyone ineligible at the unit, which includes people who CLEAR
the hours floor and fail on wages. For them `floor − hours` is negative, and the
page rendered *"-1.33 hrs"* in an amber pill. That is not an edge case:

> At Candle Bottle `GA_1134481`, **192 of 200** near-threshold employees are
> wage-bound. The top row works **36.33 hrs — above the 35-hour floor** — and
> needs **5.44** more hours a week to qualify.

So on the reference client the hours gap alone was misleading for the
overwhelming majority of the cohort, and told the worst-affected people they
were fine. `Short by` now reads `over` when the hours floor is met, and the
lever carries the real distance.

The marker is derived from the COMPARISON, not from `failure_mode`. Somebody can
fail both floors and still have the hours gap bind — 31.23 hrs at $620.90 needs
3.77 more hours for the schedule and 0.76 for the pay — and marking them would
claim the wage floor moved a number it did not.

Adding the column pushed the action button off 1024px, so `Open the walk`
became `Walk` with the sentence as its title.

## Reading the book back: three things it was asserting and could not

Found by reading the rendered page rather than by a test, the same way the
defects above were.

### Candle Bottle's TY2025 $67k was a test fixture

```
--- 1001 Candle Bottle ---
  TY2023 claimed   ident=0        avg=226.76  by=tools/backfill_gold.py
  TY2024 assessed  ident=0        avg=40      by=tests      <- leaked
  TY2025 assessed  ident=66500    avg=61      by=tests      <- leaked
```

`run_client_calculation` does not only write Gold — it dispatches
`AssessClientCommand`, which records a CLAIM.
`test_run_client_calculation` stubbed the Gold **writer** and nothing else, so
every run of that file wrote account 1001 at TY2024 and TY2025 from the
synthetic CSV into the operational store. 61 − 40 = 19 jobs × $3,500 =
**$66,500**, which is what the book showed for a client whose Gold holds only
TY2023. **964 rows** had accumulated.

The test now swaps the claim repository too, and `tools/purge_test_claims.py`
clears what was already written. A full suite run afterwards leaves the store
clean, which is the check that the leak is actually closed.

Still open, and a judgement call rather than a defect: that TY2023 claim reads
`avg=226.76` while the certified annual average is **410.13**. The claim layer
calls `domain.calculation.headcount.average_headcount`; the grid sums unit-level
One/Zero averages. Two real calculations, but the book and the client page
quote different headcounts for the same client-year.

**Resolved, and it was a defect after all.** Measured rather than reasoned
about: the claim layer hardcoded the **calendar** year as its analysis window.

```python
str(r.get("Pay_Date"))[:4] == str(tax_year)           # row selection
fiscal_window=(date(tax_year, 1, 1), date(tax_year, 12, 31))
```

Candle Bottle's payroll runs **2023-08-03 to 2024-08-09**. For TY2023 that kept
155,293 of 384,433 rows, measured at `31 Jan 2023 … 31 Dec 2023` — seven of
those dates precede the first pay date and score zero — and still divided by
twelve.

| | calendar 2023 | fiscal Aug 23 – Jul 24 |
| --- | --- | --- |
| Pay Period | **226.76** ← the claim | **494.25** ← certified |
| Min-Max | 141.40 | 410.13 |

The method accounts for ~84 jobs of the gap. The window accounts for ~268.
(The 375.53 quoted earlier in this document is the *understated* Min-Max from
the OZ-01 stub bug, not the Pay Period figure.)

**Not systemic.** Cascade, Northwind and Ironbridge are calendar filers and
agreed to the penny; Halloway is a July–June filer and was out. The one client
that is real payroll is the one that was wrong.

### Two things this nearly got wrong on the way

**`first_measurable_month`, not `window.begin`.** Passing the window's own
month reintroduced OZ-01 — a year opening mid-month opens on a stub no pay
period spans, which burns Month 1 and pushes the real final month off the end.
That reported 451.71. The fix uses the same derivation `ClientRun.engine_kwargs`
already uses, and lands on 494.25 exactly.

**The simulators had to move with it.** `average_headcount` has three callers:
the assessment and two what-if paths. Fixing one would have re-created the
Position-versus-Plan disagreement this module was written to end. All three now
resolve through one adapter, `fiscal_source.window_for_state_year`.

### A year the payroll barely touches

Widening the window surfaced a second problem: Candle Bottle's TY2024 window
runs to Aug 2025 on about **one week** of payroll, which cleared the existing
`< 50 rows` guard and published as "assessed, no credit identified".
`_MIN_MONTHS_TO_ASSESS` declines it by name, matching `_MIN_REACHABLE_MONTHS` in
the unit trend — the rule already existed, in one place only.

Candle Bottle now holds exactly one claim: TY2023, base year, `avg=494.25`,
`identified $0`.

### Why it mattered less than it looks, and more

TY2023 is Candle Bottle's base year, so `identified` was $0 before and after —
no wrong dollar ever reached a screen. But the base year is the most leveraged
input in the model. The moment a second year of payroll lands, net-new is
measured against it, and a base understated by ~268 jobs is ~$940k of credit
that was never earned, in the direction that overstates.

### The book had a year, and it was a statute year

`calculableYears` filters statute years by payroll **only when it has a
clientScope**. At portfolio scope there is none, so it returned every authored
GA year and opened on the newest — pinning every client to TY2025 whether they
hold it or not.

`YEAR_FILTERS` is now `unit` and `employee`; the scope bar is absent on the book
rather than empty. The book ranks across every year a client holds and each row
says which year it is about. That is also the honest shape of the question: an
unclaimed year from four years ago is still recoverable retroactively, and a
year filter buries it.

**It was also flattening the bands** — which is why the Band column looked
redundant. Same five clients:

| | TY2025 | all years |
| --- | --- | --- |
| Cascade | unclaimed | **exposed** |
| Northwind | unclaimed | **on_the_line** |
| Ironbridge | unclaimed | **on_the_line** |
| Halloway | declining | **declining** |
| Candle Bottle | unclaimed *(fixture)* | **settled**, TY2023 |

Candle Bottle now reads `settled` with `—` across every money column, which is
the truth: one year of payroll, and that year is its base year.

### "0.0 jobs from qualifying" about a client already over the line

`portfolioAnswer` read `gap_jobs`, which clamps at `max(0, ...)`. Northwind is
0.58 jobs **clear**, so the band named the one client on the book with nothing
to do as the closest to needing something. It reads `jobs_margin` now and says
*"Northwind Care Systems holds the threshold by 0.6 jobs"*. `nearest` also
takes the tightest margin either side rather than the first `on_the_line` row,
which was whichever one the dollar tie-break surfaced.

Same defect class as the unit grid's "Short by -1.33 hrs", and the third time a
clamped-at-zero field has been asked to carry an answer that has two sides.

## The map became a control instead of a picture

It was 546px of mostly-empty United States before the first row: we hold four
states and the other forty-six were the picture. It now sits beside a state
list — **State · Clients · Statute** — which fills the space with the thing the
map is a filter for and gives the same filter a path a keyboard can reach. A
map shape is not reachable by tab.

**Clients, not dollars.** A claim is client-grain and a client operates in
several states, so a per-state money total would either double-count or credit
a state that did not earn it.

| | before | after |
| --- | --- | --- |
| first data row | 546px | **280px** |
| rows visible at 1024x768 | 5 of 5 | **9 of 9** |

## What was NOT reached

**The legal-entity drill level (item 5) is not done.** `entity_fein` is on
`unit_year_master` and nothing reads it. Per the brief, a convincing four-level
drill beats a rushed five-level one, and the four levels are all verified above.

**The claim-derived bands still rest on invented data.** `seed_claims.py` holds
three assertions, self-described as *"Chosen to exercise every reading the
matrix can produce"*, and Cascade's `exposed` is one of them — an asserted
$95,000 against a computed $31k.

**Resolved in the same round.** The book now shows only what the engine
computed. Recoverable and exposure are both `identified − claimed`, so both
columns are gone along with the `opportunity` sort key, and `priority_band`
gates on `provenance.verified`:

```python
if self.is_exposure and self.provenance.verified:
    return PriorityBand.EXPOSED
...
outstanding = self.opportunity_usd if self.provenance.verified else self.identified_usd
```

**Gating exposure alone was not enough**, and that is the part worth
remembering. With `exposed` suppressed, Cascade's asserted $95,000 still netted
against its real $31k identified, driving `opportunity_usd` to zero and banding
a client with found credit as "Nothing outstanding" — a worse lie than the one
being fixed. Both halves are needed.

`variance_usd` and `opportunity_usd` keep their meanings. The Position view
exists to compare against an assertion and says *"vs an unverified claim"* on
screen; the band is a RANKING that puts a word next to a client's name, and
that is a different standard of proof.

Two labels changed for the same reason: `unclaimed_at_scale` reads
**Identified** rather than "Unclaimed" (whether they already claimed it is a
fact about a filing we do not hold) and `settled` reads **Nothing found**
rather than "Settled" (we computed no credit; whether anything is outstanding
is a different question). The band IDs are unchanged — they are in URLs,
filters and tests.

Live, unscoped:

| Client | before | after |
| --- | --- | --- |
| Cascade | exposed *(asserted $95k)* | **identified**, TY2021 · $73k |
| Northwind | on_the_line | on_the_line |
| Ironbridge | on_the_line | on_the_line |
| Halloway | declining | declining |
| Candle Bottle | settled | **nothing found**, TY2023 |

The book is six columns: Client · Band · Program · Year · Identified · Ask. The
band's own reading moved under its chip — jobs for `on_the_line`, the fall and
what it puts at risk for `declining` — which removed the Headline column that
had been repeating `identified` for every other row.

**The drill-down outlived the parent's cleanup**, and nothing caught it because
`ExpandedCells` had no test. It kept a Claimed column and an Outcome column
reading `over claimed` / `unclaimed` / `correctly not claimed` — every one of
which asserts something about a filing we do not hold. Both are gone; the
expanded rows are Band · Program · Year · Identified · Margin. `base year`
survives as a marker on the year, because it is the one thing Outcome said that
was not about a filing and it is why `identified` is $0 on that row.

`outcome` stays on the wire: `/api/v2/portfolio?outcome=…` is a real filter and
the Position view is built to compare against an assertion. What changed is that
the book no longer *renders* it as a finding.


`BookGrid` had **no test file at all** before this round, against a repo rule
that requires one per component. It has sixteen now.

One thing left deliberately: under a state filter the answer band still names a
client that has been filtered out. That follows the existing rule — a filter
narrows the LIST, never the answer — and changing it is a separate decision
about a rule that predates this work.

## Gate

| page | 1024x768 | 1440x900 | required |
| --- | --- | --- | --- |
| portfolio | **9 of 9** | **9 of 9** | all client rows |
| client | **13** | **18** | >= 12 |
| unit | **11** | **16** | >= 10 |

`visible == total` on the book at both viewports. The portfolio count rises from
5 to 9 because the state list is a table too; the first data row moved from
546px to **280px**. Rows 28px; the book's own rows are 35px and were before.

| Check | Result |
| --- | --- |
| dollar header reorders and changes the URL | `?bsort=identified:desc`, Halloway → last |
| band ranking still the default | `sort=priority&order=asc`, stated on screen |
| a declining client carries the band | Halloway, `declining`, rank 2 |
| the band is not `exposed` | separate value, separate tone, `exposed` still outranks it |
| map on the book, click filters | `state:NC` → 1 of 5 clients |
| held-but-unpriceable stay distinct | NC/SC/TN second shade, "no authored statute" |
| additional hours per employee | live, 192 of 200 wage-bound at `GA_1134481` |
| no fabricated figure on the book | Candle Bottle reads TY2023 · nothing found · `—` |
| no figure derived from an unverified claim | recoverable and exposure columns gone; bands gate on provenance |
| Average Headcount on the client's own year | Candle Bottle 226.76 → **494.25**, the certified Pay Period figure |
| the suite does not write to the claim store | clean after a full run |
| route inventory | **62**, unchanged |

Certified figures for account 1001 TY2023, read back through
`/api/eligibility/2023`: **10,236 employees · 539 Min-Max · 656 Pay Period.**
Unchanged.

`npm test` **432 passed** / 0 failed (was 391). `npm run build` passes.
Backend **955 passed**, 73 skipped, 1 xfailed (was 926).
`git diff backend/domain/calculation/` is **NOT** empty for the first time in
this report: `headcount.py` gained an optional `window`. The parity gate is the
check that matters and it holds — the certified path never called this function.

