# UI decisions

Context, choice and reason for each decision taken in the UI revamp (prompt
UI-01, the foundation). Newest last. The design-system reference is
[DESIGN-SYSTEM.md](DESIGN-SYSTEM.md); progress is in [UI-STATUS.md](UI-STATUS.md).

## D1. The reference palette is sampled, not invented

**Context.** The modern theme needs status colours (green, red, amber) that the
reference's published tokens do not contain; they appear only in its rendered
screenshots.
**Choice.** Sample them with Pillow from the private reference renderings and
use the sampled values as the status primitives. Where a step was not sampled
it is derived by mixing a sampled hue with white or black at a recorded ratio.
**Why.** "Nothing is invented": a plausible-looking guess is how a palette
drifts. The images are third-party and stay outside the repo; only the values
and coordinates below are recorded.

Sampled on the 1488×812 renderings (mode of a window for a background, the
most saturated pixel in a window for ink or an outline):

| Role | Value | Where (image, window x0,y0,x1,y1) |
| --- | --- | --- |
| Green tile background | `#f3fdf5` | review, 960,245,1040,255 |
| Green figure | `#4fa053` | review, 1035,252,1052,272 |
| Green outline pill border | `#d5f7dc` | review, 455,366,570,369 |
| Green pill ink | `#34643a` | review, 475,369,545,381 |
| Green result-card border | `#7ca376` | review, 616,500,618,700 |
| Red tile background | `#fcf2f1` | review, 1210,245,1290,255 |
| Red figure | `#c93b31` | review, 1322,252,1340,272 |
| Red pill background | `#f8e3e2` | review, 458,391,470,403 |
| Red pill border | `#f6d4d2` | review, 456,389,566,392 |
| Red pill ink | `#99423b` | review, 488,391,548,403 |
| Notification badge red | `#de5241` | dashboard, 1285,29,1298,37 |
| Amber star | `#f1c24e` | dashboard, 66,326,80,340 |
| Dashboard page background | `#f7f7f7` | dashboard, 5,300,25,400 |
| Card border | `#e3e3e3` | dashboard, 32,300,34,400 |
| Neutral tile background | `#f9fafc` | review, 630,245,700,255 |
| Link blue (two samples) | `#3863e3`, `#5f92ed` | review 645,706,720,722; dashboard 95,327,170,340 |
| Primary button / current step | `#3b64e4` | review, 30,682,50,690 |

Derived (recorded in `primitives.css`): green-600 = green-500 at 80% over black;
amber-50/100/200 = 12/28/50% amber over white; amber-700 = 45% amber over
black. The blue and neutral scales come from the published tokens in the
analysis document. Link blue and button blue were sampled for comparison; the
modern theme uses the published brand blue (`#4169e1`), which is within the
JPEG noise of the samples.

## D2. A colour role is `--text-default`, not `--text-body`

**Context.** The brief lists a role `--text-body`; the type scale already has a
step called `--text-body` (the 14px size).
**Choice.** The colour role is `--text-default`.
**Why.** One name for two properties would make `color: var(--text-body)` and
`font-size: var(--text-body)` both parse and both be wrong.

## D3. Base year is sky blue, not the brand blue

**Context.** The first draft aliased the base-year state to the brand blue.
`check_brand.py` (selection colour ≠ any state colour) failed on it at once.
**Choice.** `--status-base-*` uses the sky scale (100 / 800 / 300), still blue so
the meaning ("a baseline, not a finding") reads, but distinct from selection.
**Why.** A verdict that looks selected is the confusion the two-job accent rule
exists to prevent. Sky-800 on sky-100 is ~4.9:1.

## D4. The notification badge is red-500, not the sampled red-400

**Choice.** `--badge-bg` is `--red-500` (`#c93b31`); `--red-400` (`#de5241`, the
sampled badge) stays in the primitives.
**Why.** White on `#de5241` is 3.9:1 and fails AA for 12px bold text;
white on `#c93b31` is 5.4:1.

## D5. Poppins for chrome, Roboto for the data register

**Context.** Poppins is the modern default, but it runs ~10% wider than Roboto.
The widest grid (18 columns, 990px of a 987px holder) overflowed by 3–4% the
moment the face changed.
**Choice.** `--font-sans` is Poppins; `--font-data` is Roboto, applied inside
`table`, `.trend-block` and `.ui-kpi`. Bundle both.
**Why.** Density is the product's credibility; the visible-row and table-width
gates are non-negotiable. A customer overlay can point either back.

## D6. Chrome type scale

Modern: micro 12, caption 12, small 13, body 14, strong 15, subhead 16, title 24,
display 32, with line heights as tokens (`--leading-base` 1.35, heading 1.1,
dense 1.25). This is the suggested starting point, kept, with these changes to
make the gates hold:

- **Line height is a theme token.** Poppins' natural line box is ~28% taller
  than Roboto's; an unset line-height spent that on every line. Tailwind's
  preflight sets `html { line-height: 1.5 }`, so classic is 1.5 (not
  `normal`) and renders as it did.
- **Inside the dense page header and `.ui-kpi`, `--text-display` collapses onto
  `--text-title`.** At 32px both pushed the first grid row below the fold.
  The hero band and other roomy surfaces keep the full size.
- **The data register** (D5) collapses micro..strong onto `--text-data` inside a
  table or location block, so a pill or sub-label in a cell cannot outgrow its
  12px column.
- **`.pill` horizontal padding is a theme token** (`--pill-pad-x`, 8px modern,
  10px classic): the register holds a pill at 12px (was 11px), which widened
  the Reading column by 6px; the padding gives it back.

## D7. Data selectors move to `--text-data` (step 1), then the chrome scale
##     is re-valued (step 2)

Step 1 migrated every selector that renders data (cells, headers, figures,
verbatim engine output) from `--text-body` / `--text-strong` to `--text-data`
before any value changed. Under the classic theme the metrics were identical to
the baseline (see UI-STATUS.md); only then was the modern scale introduced.

## D8. Where the line is between "migrate" and "leave for the page work"

The brief says to migrate only literals in files touched and not to mass-rewrite
`index.css`. Three things were migrated beyond that because the brief also says
"one implementation of each":

- `StatCard`/`StatRow` and three hand-rolled `kpi-card` markups → `KpiTile`.
  Tone names changed from colour words (good, warn, bad, accent) to state
  families (above-min, partial, below-min, neutral); the old "accent" tile had no
  reading and is neutral. A tiny `lib/kpiTone.js` maps the old spellings for
  `ReferenceViews`, which still passes them.
- `MethodTabs`, `GridTabs`, `SectionTabs` and two hand-rolled `.tabs` rows →
  wrappers over `Tabs`.
- The left rail's hard-coded inverse text colours → `--text-inverse-*` roles, because
  the contrast gate caught 1.9:1 hints on the new navy. (The rail itself is
  replaced in the next prompt.)

**Left for the page work, deliberately:** the legacy `.pill-*` classes (used in
dozens of JSX sites) remain beside the new `Pill`; they now read the same state
tokens and a theme padding token. Migrating the call sites is page work and a
mass edit here would be unreviewable.

## D9. Contrast is enforced for modern, reported for classic

`check_contrast.py` fails the build for the modern theme. The classic theme is
the previous look, preserved as it was (its muted greys predate the gate); its
offenders are printed but do not fail. `TCC_STRICT_CLASSIC=1` makes them fail.

## D10. The app cannot boot on a clone without private inputs

**Context.** The shell needs the sealed reference workspace (`One.csv`..) and
every per-client read needs the Fabric Warehouse, neither of which is in the
public repo, so "synthetic data" alone renders "Workspace unavailable".
**Choice.** `frontend/tools/mock_api.py`: a stdlib stand-in on :8000 serving a
small invented dataset for exactly the endpoints the gates need, forwarding the
rest to a real backend on :8001. No tool changed its URLs.
**Why.** The gates need a rendered page; faking the whole API in each tool would
have forked them. All figures in it are invented and carry no certified value.
The baseline and the "after" numbers were taken against the same stand-in, so
they are comparable; absolute row counts are the stand-in's, not the product's.

## D11. Working branch and commits

The work ran in the session's git worktree (`jamesiford-ui-01-foundation`, cut
from `feat/ui-modern-theme`), not in a separate `wp/UI-nn-*` branch per work
package. Commits are small and labelled `<type>(UI-01x)`, and nothing was
pushed. Each package's evidence is in UI-STATUS.md.

## D13. Layout audit, and 1440×900 as the acceptance viewport (owner-directed)

**Context.** Reviewing the first modern skin, the owner flagged a button whose
icon and label broke onto two lines, said the result was not comparable to the
reference (which is much cleaner and less cluttered), and asked for 1440 as the
frame that shows the full width, with mobile out of scope.
**Choice.** (1) Fix the root cause of the icon bug (the preflight `svg { display:
block }`) for both themes. (2) Re-skin the shell and page chrome calmly in
`chrome-modern.css` (see DESIGN-SYSTEM.md, "Layout and spacing: the calm pass").
(3) Make 1440×900 the only gated viewport: every tool defaults to it and
`check_all.py` holds the visible-row gate at the pre-revamp 7 / 13 / 17 rows
there. The 1024×768 gate is dropped.
**Why.** The gate exists to protect "the partner sees their data without
scrolling"; at 1440 that is still measured, and still passes, with more air
around the data. Rows were recovered by tightening only the blocks that are not
data (page-bar gap, header gap, KPI tile padding, the padding of a panel that
holds a grid), never the grids.
**Not done here, deliberately.** A top navigation, hero band and task cards are
the next prompt's structure; the rail is restyled, not removed. (Done in D14–D17.)

## D14. The shell is a top bar, a drill trail and a launcher (UI-02)

**Context.** The reference has a top navigation and no rail; the rail cost 216–248px
of width and held two lists (the drill ladder and "prove the work") that read as
one menu.
**Choice.** `components/shell/`: `TopBar` with three `NavGroup` dropdowns (one per
NAV section), `DrillTrail` under it, `ShellActions` (year scope, account menu),
`AppShell` (skip link, `<header>`, one `<main id>`), and a `FloatingAction`
"Ask Copilot" (Ctrl+K kept). The rail's drill rules moved verbatim to
`lib/drill.js`; `SideRail.jsx` is deleted. Mobile (drawer, scrim, hamburger) is
gone with it: out of scope.
**Why.** The width goes back to the data, and the trail answers "where am I" on
every page in one line. `NAV` is unchanged (3 sections, 8 items); only `eligibility`
gained `needsClient`, so it is disabled with a reason at the book instead of
hidden.
**Consequences.** The group menus are menu buttons, so tests open a group and
then pick a `menuitem` (`App.test.jsx` `goToView`). The account menu exists only
when `/api/me` says somebody is signed in (AUTH_MODE=entra); with `none` there is
no identity to show and no stand-in "guest".

## D15. One trail, not two: `showTrail`

The page `Breadcrumb` would have repeated the `DrillTrail`. Pages take
`showTrail` (default `true`, so a page rendered alone still has its breadcrumb)
and the shell passes `false`. The claim-package button, which shared a row with
the breadcrumb, now sits on the client tabs row, and `.tcc-page-bar` is only
rendered when the breadcrumb is.

## D16. The home hero replaces the page header; the `ptab` deep link is obsolete

`PortfolioPage` is a single grid with no tabs, and `portfolioAnswer` returns
counts only, so the brief's `?ptab=call&focus=` deep link has nothing to land on.
The "Who to call" card scrolls to and focuses the book's "Targeting" heading
instead. The hero owns the page's `h1` ("Hi, Jane" / "Welcome back"); "Targeting"
is the book's `h2`, so the outline stays valid and `App.test.jsx` still finds it.
"Start here" defaults to open the first time and is remembered
(`lib/startHere.js`). The cards are real links, so a modified click opens a tab.

## D17. Backend used for measurement

The stand-in on :8000 forwarding to a real backend on :8001 (`DATA_SOURCE=csv`),
as in D10. Pointing the app at the real backend alone cannot boot the shell: it
needs the sealed reference workspace and the Warehouse, neither of which is in a
clone. Figures are comparable with the baseline, not with production.

## D12. Node 26 and the unit tests

On Node ≥ 25 an experimental `localStorage` shadows jsdom's, so 14 `App` tests
fail on `localStorage.clear`. The supported runtime is Node 24. Rather than
edit those tests, the tools run vitest with
`NODE_OPTIONS=--no-experimental-webstorage` and the README says why.
