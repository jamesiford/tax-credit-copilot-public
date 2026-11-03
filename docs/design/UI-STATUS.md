# UI status

Prompts UI-01 (foundation) and UI-02/UI-03 (shell and home) of the modern-theme
revamp. Branch `jamesiford-ui-01-foundation` (cut from `feat/ui-modern-theme`);
nothing pushed. Decisions and reasons: [UI-DECISIONS.md](UI-DECISIONS.md).
Reference: [DESIGN-SYSTEM.md](DESIGN-SYSTEM.md).

## Work packages

| WP | Scope | State |
| --- | --- | --- |
| UI-01a | Token layers, modern and classic themes, Poppins, type/space/radius/shadow scales, data register, deprecated-alias ratchet | done (`f1c83e9`) |
| UI-01b | 15 base components + tests; `MethodTabs`/`GridTabs`/`SectionTabs` on `Tabs`; `StatCard` and three `kpi-card` markups on `KpiTile`; `PageHeader` meta slot; dev-only `/__styleguide` | done (`cfb9d33`) |
| UI-01c | Tooling: `check_tokens`, `check_contrast`, per-theme `check_brand`, extended `design_metrics`, `check_all`, theme-aware tools, `mock_api` | done |
| UI-01d | Docs: `DESIGN-SYSTEM.md`, overlay docs, Frontend rules in `copilot-instructions.md` | done |
| UI-01e | Layout audit and calm pass (owner-directed): icon-beside-label fix, light shell, rhythm, 1440×900 acceptance viewport | done |
| UI-02 | Top bar, three dropdown nav groups, drill trail, account menu, floating Ask launcher, skip link; `SideRail` deleted | done |
| UI-03 | Home hero, four task cards, persisted "Start here" | done |

No work package is blocked.

## UI-02 / UI-03

Measured at 1440×900 against the offline stand-in (D10, D17). "Before" is the
state at the end of UI-01 (rail shell).

| Page | Visible rows before → after (modern) | First-row y before → after (modern) | Visible rows (classic) |
| --- | --- | --- | --- |
| Portfolio (7 rows in the book) | 7 → 7 | 280 → 398 expanded, 318 collapsed | 7 |
| Client | 13 → 13 | 308 → 295 | 15 |
| Unit | 17 → 17 | 424 → 415 | 17 |

At 1024×768 (smoke only, no row gate; no horizontal overflow on any page):
portfolio 7, client 11, unit 9. The unit page loses rows there because its tiles
wrap; at the pre-revamp baseline it showed 12. Not gated, recorded.

**Expanded "Start here" and the fold.** The book has seven rows and all seven are
visible either way, so the gate passes expanded. With a longer book the cards
would push rows below the fold: that is why the collapsed state is the one the
gate is meant to defend, and why it is remembered once chosen.

**Tests.** 739 → 798, no skips. Selectors that changed:
`App.test.jsx` `goToView` (a rail button became "open the group, pick the
`menuitem`"), and a `fetchMe` stub. New: `NavGroup` (keyboard and ARIA),
`DrillTrail` (each level), `shell.test.jsx` (every `NAV` id reachable, disabled
with a reason, skip link and focus order, landmarks, account menu), and
`portfolioHome.test.jsx` (hero → cards → grid, routing, collapse persists).
`tokens.test.js` ceilings lowered (`--exp-magenta` 8→6, `--exp-gold` 9→6,
`--exp-violet` 1→0); deprecated aliases 226 → 220.

**Selectors removed from the CSS:** `.tcc-topbar`, `.tcc-brand`, `.tcc-top-context`,
`.tcc-top-btn`, `.tcc-mobile-menu`, `.tcc-nav-scrim`, `.tcc-siderail`,
`.tcc-rail-*`, `.tcc-rung*`, `.tcc-has-rail`, `--rail-w`, and the matching
`chrome-modern.css` sections. The tools' selectors were updated:
`measure_ui.py` reports `.shell-header` height instead of the sidebar width, and
`sweep.py` clicks the trail's "Portfolio".

**Routes:** unchanged. `NAV` is still 3 sections and 8 items.

**Known gate failure, not from this work.** `gitleaks detect` scans every ref in
the repository and reports three `generic-api-key` hits in
`channel_orchestrator/app/vendor/tcc_shared/MANIFEST.json`, introduced by
`c6de10f` on another branch (not an ancestor of this one). It is almost
certainly hashes in a manifest. `gitleaks detect --log-opts=HEAD` finds no leaks
on this branch. The gate was left as is.

## Baseline (before any change; same offline stand-in, see D10)

Backend untouched. Taken on Node 26 with `--no-experimental-webstorage` (D12).

| Metric | Baseline |
| --- | --- |
| `npm test` | 600 passed (14 fail on Node 26 without the flag) |
| `npm run build` | js 664.14 kB, css 134.97 kB (+ Roboto 400-800) |
| Visible rows 1440×900 (portfolio / client / unit) | 7 / 13 / 17; first-row y 238 / 319 / 403 |
| Visible rows 1024×768 | 7 / 10 / 12; first-row y 242 / 323 / 425 |
| Smallest rendered data text | 12.0px |
| `design_metrics` (index.css) | 9 distinct radii / 139 uses, 5 raw-px padding/margin, 2 inline styles |
| `check_brand` | Roboto everywhere; no Google font requests |
| `sweep.py` | 81 states, 44 FAIL, 5 WARN, 32 PASS (the stand-in's limits; the gate is "no more FAIL") |

Step 1 of the type work (data selectors → `--text-data`) was measured under the
classic theme before any value changed: **identical** to the table above.

## After

| Metric | After |
| --- | --- |
| `npm test` | **739 passed** (+139) in 56 files, no skips added |
| `npm run build` | js 663.84 kB, css 152.93 kB; `/__styleguide` absent from the bundle |
| Visible rows 1440×900, modern | **7 / 13 / 17** (= baseline); first-row y 280 / 308 / 424 |
| Visible rows 1440×900, classic | 7 / 13 / 17 (= baseline); first-row y 244 / 310 / 417 |
| Smallest rendered data text | 12.0px, both themes |
| Cells clipped / tables overflowing | 0 / 0, both themes |
| `check_brand` | 0 problems both themes; base-year vs below-min ΔE 65 (ink) and 38 (line); no selection colour equals a state colour |
| `check_contrast` | 0 pairs below AA (modern); classic reported only |
| `check_tokens` | 0 problems in 16 stylesheets |
| `design_metrics` | 0 raw-px font sizes; 5 raw-px padding (unchanged); 2 inline styles (the two documented exceptions); deprecated aliases 233 → 226 |
| `sweep.py` | 44 FAIL (= baseline) |
| `check-whitelabel -Enforce` / `audit-export --enforce` / gitleaks | pass / pass / no leaks |

Full gate: `python frontend/tools/check_all.py` → **20/20 passed**.

### Deprecated-alias ratchet (`src/lib/tokens.test.js`)

`--exp-primary` 36 · `--exp-accent` 12 · `--exp-magenta` 8 · `--exp-subtle-2` 10 ·
`--exp-muted` 12 · `--exp-blue` 10 · `--exp-subtle` 4 · `--exp-ink` 3 ·
`--exp-gold` 9 · `--exp-violet` 1 · `--accent` 20 · `--accent-strong` 26 ·
`--accent-bg` 3 · `--accent-2` 1 · `--accent-2-strong` 41 · `--accent-2-bg` 26 ·
`--accent-2-line` 4. The next prompts shrink these.

## Final type scale (and why)

Modern: micro 12 · caption 12 · small 13 · body 14 · strong 15 · subhead 16 ·
title 24 · display 32; data 12. Classic keeps 9/10/11/12/13/14/18/22. The
suggested starting point was kept; the changes that make the gates hold are
D5 and D6 (data register, Roboto for data, line height as a token, display
collapsing to title inside the dense header and tiles).

## Components

**Added** (`src/components/ui/`, each with CSS and a test): `Button`, `Card`,
`Pill`, `CountBadge`, `Tabs`, `KpiTile`/`KpiRow`, `Callout`, `Stepper`,
`TaskCard`, `HeroBand`, `MetaLine`, `SectionHeading`, `FloatingAction`,
`EmptyState`, `Skeleton`.

**Deleted / merged:** `StatCard.jsx` (→ `KpiTile`); the hand-rolled `.tabs` rows
in `ReferenceViews`; `Kpi` in `TrendGridView` (dead); the `.kpi-card`,
`.tcc-stat*`, `.method-tabs button`, `.grid-tab-count` and `.section-tabs button`
rules. `MethodTabs`, `GridTabs`, `SectionTabs` remain as thin wrappers.

**Existing tests whose selectors changed, and why:** `PositionView.test.jsx`
(`.tcc-stat*` → `.ui-kpi*`), `UnitPage.test.jsx` (`.tcc-stat` → `.ui-kpi`),
`AgentActivityView.test.jsx` (`.kpi-card` → `.ui-kpi`): the figure tile is a
different component. `pageComposition.test.jsx` now reads the section tabs from
the "Client sections" tablist, because the reading and population switches are
tabs too. No assertion was weakened.

**Still two of something (deliberate, D8):** the legacy `.pill-*` classes beside
`ui/Pill`; they read the same state tokens and move with the page work.

## Files

Added: `src/styles/tokens/*` (7 files), `src/styles/chrome-modern.css`,
`src/styles/overlay.css`, `src/components/ui/*` (47), `src/pages/Styleguide.*`,
`src/lib/tokens.test.js`, `src/lib/kpiTone.js(.test)`, `tools/_theme.py`,
`tools/check_tokens.py`, `tools/check_contrast.py`, `tools/check_all.py`,
`tools/mock_api.py`, `tools/shoot_pages.py`, `tools/README.md`, and
`docs/design/{DESIGN-SYSTEM,UI-DECISIONS,UI-STATUS}.md`.
New runtime dependency: `@fontsource/poppins` (SIL OFL), latin 400/500/600/700.

## Sampled status colours

See D1 in UI-DECISIONS.md (values and image coordinates).

## For the owner to review visually

Screenshots are in the gitignored `frontend/tools/sweep-output/`:
`before/` (baseline, both viewports), `after-modern/` and `after-classic/`
(1440×900, ten pages each), and `sg-modern.png` (the style guide). Look at:

- The portfolio and client pages at 1440 against the reference: top bar, rail,
  page header rhythm, the map block, the grid header row.
- `/__styleguide` (run `npm run dev`) in both themes.
- Anything that still carries a coloured stripe or a heavy label: the
  verdict stripes were kept on purpose, everything else should be a hairline.
- The employee and agents pages in the screenshots show errors because the
  offline stand-in does not serve them; they are not regressions.
- The shell is a top navigation with a drill trail, a hero and task cards on
  `/` (UI-02/UI-03). Look at the menus open, the trail at each level, and the
  home page with "Start here" open and closed (`modern-*-1440.png`,
  `home-expanded.png`, `home-collapsed.png`, `home-menu.png`).
