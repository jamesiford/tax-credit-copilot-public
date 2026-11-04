# GHCP prompts — UI/UX revamp

## HOW TO RUN THIS UNATTENDED

Three phases: **7 skeleton · 8 density · 9 brand.** Run in order. They are
layers on the same surface — 7 restructures the shell, 8 fills it with dense
tables, 9 skins it — so a failure in an early phase makes the later ones
meaningless.

**Rules for an unattended run:**

1. **Commit after each phase.** Separately, with a real message. This is the one
   non-negotiable rule: without it a bad phase 9 cannot be reverted without
   losing 7 and 8. A harmful edit mixed into the same commit as good work cannot
   be undone with `git checkout`.

2. **Stop on a failed gate.** If a phase's gate does not pass, commit whatever
   works, write the report, and STOP. Do not begin the next phase on a broken
   foundation. Half a revamp that works beats a whole one that does not.

3. **Verify current state before building.** Parts of this brief have already
   been delivered by earlier prompts, and the figures below were measured at
   different times. Check before you build, and say in the report where the
   brief was already satisfied.

4. **Do not browser-verify after every change.** Warm page loads were ~20s
   before the perf fix. Verify once per phase, at 1024×768.

5. **Decisions already made — do not stop to ask:**
   - `PageHeader.jsx` / `StatCard.jsx` may already exist. Evaluate and adopt or
     replace; do not create a third variant.
   - The brand asset hub is not reachable. **Approximate** the support
     and tertiary palettes from the wordmark blue and the named colours, and
     document each approximation in a comment.
   - Squircle assets are not reachable. Pick ONE border-radius token, apply it
     everywhere, note it as an approximation.
   - The 36-row client grid does **not** paginate. Its length is the point.
   - Delete the standalone ProgressView section only once the in-grid row
     treatment genuinely carries the answer. If it does not land, leave
     ProgressView alone and say so.

6. **Write `docs/design/REVAMP-REPORT.md` at the end.** Nobody is watching this
   run. For each phase record: what changed, the gate result with numbers, what
   was already done, what was skipped and why, and anything that changed meaning
   rather than appearance.

**Standing constraints, every phase:**

- Do not modify `backend/domain/calculation/*`. `git diff` there must stay empty.
- Never edit an expected test value to make something pass. The certified
  figures are 10,236 / 539 / 656.
- Frontend only. The backend is settled.
- Evidence, Compare and Methodology are SEALED — pinned to the certified run,
  and must not follow the client selector.
- If a claim in this brief does not match the code, STOP and record it rather
  than building on it.

---

Written 8 Sep 2026. Target: **1024×768**, primary user the partner's consulting team —
dense, data-rich, numbers tell the story. The partner's product, the partner's brand.

Measured on the running app at 1024×768 before writing these:

    sidebar               196px   19.1% of the viewport
    content width         820px   (1016px without the sidebar, +24%)
    first data pixel      y=747   of 768
    visible data           21px
    scope bar             150px   (axes 49 + derived 26 + notices 35)
    page scroll            1.7 screens

Run in order. Commit between each.

---

## 7. The skeleton — kill the sidebar, reclaim the fold

```
At 1024x768 this app shows TWENTY-ONE PIXELS of data. Measured: the first table
row sits at y=747 of 768. Everything above it is chrome.

The left nav costs 196px — 19.1% of the screen — permanently. Nothing in it
appears in the primary workflow: portfolio -> client -> unit -> employee is a
drill driven by clicking data, not by navigating.

THE KEY INSIGHT: the URL is the scope. At /c/2001 the client selector in the
scope bar duplicates the breadcrumb. That bar exists because the app had no
routing when it was built. It does now.

--------------------------------------------------------------------------
BUILD THIS
--------------------------------------------------------------------------
  ┌──────────────────────────────────────────────────────────────┐
  │ [brand] │ Tax Credit Copilot    TY2023 ▾  Min-Max ▾  ⌘K  ⋯ │ 52px
  ├──────────────────────────────────────────────────────────────┤
  │ Portfolio › Cascade Retail › GA_GA-010        [Run] [Ask]    │ 36px
  ├──────────────────────────────────────────────────────────────┤
  │ 20 counted in May · 8 within 5 hrs of the 35-hr floor        │ 48px
  │ run 1ef6698 · 2026-09-08 04:01 · rules/ga_jtc/2023.json      │
  ├──────────────────────────────────────────────────────────────┤
  │                     632px of data                            │
  └──────────────────────────────────────────────────────────────┘

136px of chrome, down from 747px. Content width 992px, up from 820px.

Only TY and method live in the top strip — they are the two things that persist
across a drill. Client comes from the URL.

--------------------------------------------------------------------------
REHOME THE EIGHT NAV ITEMS — nothing is deleted
--------------------------------------------------------------------------
  'eligibility'  Who qualifies      -> TAB on the client page. It is the
  'onezero'      One/Zero detail       Min-Max vs Pay Period comparison — the
                                       539/656 split — and it is client-scoped.
                                       NOTE: OneZeroView falls back to
                                       fetchWorkspaceOneZero when no client is
                                       selected. That is a SEALED read. Preserve
                                       it.

  'evidence'     Evidence pack      -> reachable from the PROVENANCE LINE that
  'compare'      Compare to Access     every page already renders. Click the run
  'rules'        Rules & statute       id -> Evidence. Click the rule pack ->
  'assumptions'  Methodology           Rules. That is where someone asks "where
                                       did this number come from", so that is
                                       where the answer belongs. Also list them
                                       in the ⋯ menu so they are discoverable.

  'ingestion'    Data ingestion     -> ⋯ menu. Occasional, operational.
  'agents'       Agent activity     -> ⋯ menu.

Evidence, Compare and Methodology are SEALED — pinned to the certified run, and
they must NOT follow the client selector. They call fetchWorkspaceAssumptions /
fetchWorkspaceCalculationWalk / fetchWorkspaceComparison, which take no client
argument, so the property holds structurally. Do not add one.

--------------------------------------------------------------------------
⌘K OPENS ASK COPILOT, SCOPED TO THE PAGE
--------------------------------------------------------------------------
Not a nav jumper — the context-aware agent. api/chat.py:44 already accepts
client_id, tax_year and method, so the page passes what it is showing and the
agent answers over the same client-year on screen.

⌘K anywhere opens it. Esc closes. Keep the existing "Ask about this page"
seeded prompt per route.

--------------------------------------------------------------------------
RULES
--------------------------------------------------------------------------
- Breadcrumb and page actions share ONE line. Today the heading stack is
  breadcrumb -> client name -> eyebrow -> orphan pin icon -> title, and on
  UnitPage the unit id appears twice.
- The scope bar's warning notices ("TY2026 held, not priceable") move into the
  answer band or the year selector, not a third band.
- Deep links must still resolve cold:
  /c/2001/u/GA_GA-010?year=2023&month=5
- Employee ids never appear in a URL. record_token is the handle.
- Keep the three calculation states: calculated / not_calculated / zero.

GATE — measure, do not eyeball. At 1024x768 report the y-coordinate of the
first table row on all four pages. Target under 150px.

Run `npm test` and `npm run build`.
```

---

## 8. Density — make the numbers the interface

```
The partner's team read spreadsheets. Give them one. Every table in the app is
currently styled like a marketing page.

--------------------------------------------------------------------------
DENSITY TOKENS — define once, apply everywhere
--------------------------------------------------------------------------
  row height        28px      (not 44)
  body / label      13 / 11px
  header            24px, uppercase 11px, STICKY
  cell padding      8px horizontal
  numerics          font-variant-numeric: tabular-nums; right-aligned
  separators        hairline rows OR zebra — never both

28px rows against 632px of data = 22 rows visible without scrolling.

--------------------------------------------------------------------------
CLIENT PAGE — the holy grail grid, EXPANDED BY DEFAULT
--------------------------------------------------------------------------
Unit x year x twelve months, every row visible. Cascade is 6 units x 6 years =
36 rows. That is the point: the whole client on one scroll.

UNIT      YR   J  F  M  A  M  J  J  A  S  O  N  D   AVG   BASE  NET-NEW MIN STATUS  CREDIT
GA-001  2020  18 18 18 19 18 18 18 18 19 18 18  0  18.33    —      —     2  base        —
        2021  25 25 26 25 26 25 26 25 25 26 26  0  25.50  18.33  7.17    2  above  $25,095
        2022  26 26 27 26 26 26 26 27 26 26 26  0  26.17  18.33  7.84    2  above  $27,440

Column budget at 992px:
  unit 88 · year 44 · 12 months x 30 = 360 · avg 56 · base 56 · net-new 68
  · min 40 · status 72 · credit 88  =  872px, 120px spare

The month-12 zeros are REAL and must stay visible — that is the measuring-date
cliff, and it is a finding the partner needs to see, not a rendering bug.

Group rows by unit with the unit cell spanning its years. Base year row reads
differently from qualifying years.

--------------------------------------------------------------------------
"HOW AM I DOING" IS NOT A SEPARATE SECTION
--------------------------------------------------------------------------
It is the question "will I average what I need to be eligible?" — an in-year
projection against the threshold. The grid already has the shape: the current
year is a partially filled row.

Project that row forward and show the answer in place: projected average,
whether it clears MIN, and how many months are closed. /api/progress/{year}
returns this — it carries the projection plus base_caveat plus a near_the_line
cohort.

Mark it unmistakably as an ESTIMATE. A run-rate projection rendered with the
same confidence as a calculated figure is how somebody files against a number
that was never a calculation. ProgressView says this in three places today;
keep all three.

Delete the standalone ProgressView section from the client page once the row
treatment carries it.

--------------------------------------------------------------------------
PORTFOLIO — five rows, sorted by who to call
--------------------------------------------------------------------------
CLIENT          STATUS      LOC  BASE   NET-NEW  GAP   IDENTIFIED  CLAIMED  VARIANCE  LAST RUN
Ironbridge      assessed      4  TY2021    1.17  0.83    $248,500      —    $248,500  2d ago
Cascade Retail  assessed      6  TY2020    7.59    —     $607,110      —    $607,110  today
Candle Bottle   claimed     101  TY2023      —     —           $0  $410k   not comp.  today
Northwind Care  not calc'd    5     —       —      —            —      —          —   [Run]

Candle Bottle's row was drafted with a large identified figure and a variance
against the filed amount, computed against a base of zero. We hold one fiscal
year for that client, so its earliest year is its own baseline and net-new is
zero by construction — the figure was an artifact of the missing base, and a
variance against a filed amount is not computable in a baseline year. The other
rows are illustrative.

Default sort: GAP ascending. Never dollar value — a client one hire short is
worth $0 today, the same $0 as one fifty jobs short, so ranking by value buries
the one to call. Say that on the page.

Unassessed rows carry NULL, rendered as "—" with a Run action. Never $0.
Use total_clients / assessed_clients from the API, not row counts.

--------------------------------------------------------------------------
UNIT — two tables, the second one matters more
--------------------------------------------------------------------------
COUNTED (20)
EMPLOYEE     WEEKLY HRS  WEEKLY $   WKS   J F M A M J J A S O N D
200100243        54.47   $1,976.53   52   1 1 1 1 1 1 1 1 1 1 1 0

── WITHIN 5 HRS OF THE FLOOR (8) ────────── floor: 35.0 hrs / $636 ──
200100366        34.29   $1,034.29   52   0.71 short
200100056        34.10     $727.70   52   0.90 short

Both sorted by weekly hours desc. The near-threshold table gets the visual
weight — it is the actionable one, and at GA_GA-010 the closest is 0.71 hours
short. Floors come from `thresholds`, never hardcoded.

--------------------------------------------------------------------------
EMPLOYEE — why, then what-if
--------------------------------------------------------------------------
Pay periods with selection_decision as a real column: "outside fiscal window",
"shorter than seven days", "filtered by pay code" are three different answers
and a reviewer must tell them apart.

Then the what-if levers: adjust this person's hours and wages, show the
eligibility flip live against both methods. This is the last step of the demo
narrative — "how tweaking hours and wages affects eligibility".

Run `npm test` and `npm run build`. Verify at 1024x768.
```

---

## 9. Brand — the partner, not Microsoft

```
This is the partner's product wearing Microsoft's font. Fix that first, then the
palette.

Sourced from the partner's brand central, 8 Sep 2026.

--------------------------------------------------------------------------
1. ROBOTO
--------------------------------------------------------------------------
"We use Roboto online when a font is required to be loaded such as our
websites, products or apps."

index.css:11 currently sets 'Segoe UI'. Roboto is a free Google font — self-host
it, do not hotlink. DIN Next is print-only and licensed; Arial is for Office.
Neither belongs here.

This is the single largest credibility gain available and it is one @font-face.

--------------------------------------------------------------------------
2. "We are a blue and purple brand"
--------------------------------------------------------------------------
Their words. Blue is the core thread and runs through the wordmark. But:
"A selection of warm purple, raspberry and magenta tones also plays an important
part in our palette and SHOULD BE USED GENEROUSLY."

The app defines --exp-purple and --exp-magenta and then a comment restricts them
to "brand chrome only". That runs against the guide and leaves the UI
monochrome blue — which reads as a Microsoft product.

Let purple and magenta carry accents, active states, and the answer band.

--------------------------------------------------------------------------
3. Retire the remaining hex literals
--------------------------------------------------------------------------
Re-measured 8 Sep 18:05, after the design-system commit (657552c):

  index.css     161 hex literals · 39 tokens   (was 294 hex · 24 tokens)

Real progress — roughly half the drift is gone and the token set grew. Finish
it. Re-count before you start; the number will have moved again.

  #26478d  -> var(--exp-primary)  ALREADY A TOKEN if still written raw
  #b52e87  -> var(--exp-magenta)
  #1d3972  -> the drill header, not in the palette at all

Watch for near-duplicate greys — #e6e6ef, #f7f8fc, #f4f5f9, #fafbfd, #f7f7fb,
#f8f9fc, #8a8aa0 were all present and are doing the work of --line, --bg and
--muted. Nobody can name the difference between #f7f8fc and #f8f9fc. That is
drift, not design, and it is exactly what makes a UI feel almost-designed.

Target: no hex outside :root. Any survivor needs a comment saying why.

--------------------------------------------------------------------------
4. Colour must mean something
--------------------------------------------------------------------------
"The Tertiary palette ... is primarily used for data visualisations, charts and
graphs. They should never be the dominant colour in any design."

So the KPI cards stop carrying saturated colour. Today blue marks Exposure,
Cells assessed AND Unverified — three unrelated things — while green marks
Recoverable. Either the tone encodes the reading or every card is neutral.
Neutral is the brand-correct answer.

The partner's Alert Red and Alert Green exist for genuine alert states. Reserve them.

Body copy is GREY on white, per the guide. The app uses --ink #1a1f36, a
near-black navy. Soften it.

--------------------------------------------------------------------------
5. One component each
--------------------------------------------------------------------------
Three KPI card treatments -> one <StatCard tone>. An absent value ("—") should
recede, not match the weight of $416,535.

Six header treatments -> one <PageHeader>: eyebrow, title, subtitle, action.

Four callout styles -> one <Callout tone> plus the answer band, which stays
distinct because it is the page's headline.

PageHeader.jsx and StatCard.jsx already exist uncommitted in the tree — check
whether they are the right shape before writing new ones.

--------------------------------------------------------------------------
6. Squircles and white space
--------------------------------------------------------------------------
The partner's shape language is the squircle — a superellipse, softer than a
rounded rect. Approximate with a consistent border-radius token rather than
guessing per component. One radius, used everywhere.

"The deliberate, generous use of white space provides a sense of calm and
confidence." At this density that lives in MARGINS AND LINE-HEIGHT, not empty
bands. Dense and calm are not opposites — the current app is dense and noisy.

--------------------------------------------------------------------------
RULES
--------------------------------------------------------------------------
- Visual only. Do not change any figure, any copy stating a number, or any
  calculation.
- Backend untouched.
- Sealed views keep their behaviour.
- `npm test` after each page, not once at the end.

Finish at 1024x768 AND 1440x900. Report anything that changed meaning rather
than appearance.
```
