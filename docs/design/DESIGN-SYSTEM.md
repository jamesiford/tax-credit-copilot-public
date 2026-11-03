# Design system

How the portal looks is decided in one place per layer, so that changing a
palette, a typeface or a whole theme never means editing a component. This is
the reference for those layers, the component set, the two density registers,
the accessibility rules and the gates that defend them.

The rules the code must obey are in `.github/copilot-instructions.md`
("Frontend rules"); this file explains the system they describe. History of
earlier rounds is in [REVAMP-REPORT.md](REVAMP-REPORT.md) and
[UI-REVAMP-BRIEF.md](UI-REVAMP-BRIEF.md); decisions taken in this revamp, with
their reasons, are in [UI-DECISIONS.md](UI-DECISIONS.md); progress and measured
numbers are in [UI-STATUS.md](UI-STATUS.md).

## Token layers

`frontend/src/styles/tokens/`, imported first from `main.jsx`:

| File | Holds | Rule |
| --- | --- | --- |
| `primitives.css` | Raw scales: denim, brand, sky, teal, cadet, grey, and the sampled status greens, reds and ambers. | No meaning. Nothing outside `styles/tokens/` references a primitive. |
| `scales.css` | Spacing (`--space-1..16`), the data register (`--text-data`, `--row-height-data`, `--cell-pad-data`), stacking, motion, floating offset. | No theme re-values these. |
| `theme-modern.css` | The default look. Assigns every semantic role from primitives; also chrome type, radius, shadow, line height. | `:root` as well as `html[data-theme="modern"]`, so it is the default when no attribute is set. |
| `theme-classic.css` | The previous look, kept so the revamp can be rolled back by configuration. Same roles, the old values. | Its literals live only here. |
| `semantic.css` | The legacy vocabulary (`--ink`, `--line`, `--panel`, `--ok`...) as aliases of roles, plus the **deprecated** `--accent*`, `--accent-2*`, `--exp-*`. | Counted by a ratchet (below). |
| `state.css` | The five `--state-*` families, each with `-ink` and `-line`. | Aliases `--status-*` roles; restates no literal. |

The layering is **primitive → role → component**. A theme is nothing but
assignments of roles from primitives, so a component never knows which theme is
active.

### Roles

- **Text:** `--text-primary` (headings, figures), `--text-default`,
  `--text-secondary`, `--text-muted`, `--text-link`, `--text-inverse*`.
  (`--text-default`, not `--text-body`: that name is the 14px type step.)
- **Surfaces:** `--surface-page|card|subtle|raised|tint|hero|brand-soft|inverse`.
- **Borders / icons:** `--border-default|subtle|strong|brand`, `--icon-primary|brand|muted`.
- **Selection:** `--select`, `--select-strong`, `--select-bg`, `--select-line`,
  `--on-select`, `--focus-ring`.
- **Readings:** `--reading`, `--reading-strong`, `--reading-bg`, `--reading-ink`.
- **Identity:** `--identity-start|end|end-strong` (header gradient, primary button).
- **Status:** `--status-{base,ok,bad,warn,neutral}-{bg,ink,line}`,
  `--status-ok|warn|bad|info` and `--status-info-bg`.
- **Charts and map:** `--chart-1..6`, `--chart-grid|track`, `--map-*`.
- **Shape:** `--radius-sm|--radius|--radius-lg|--radius-xl|--radius-pill`
  (8/12/16/20/pill modern; 3/5/8/12 classic), `--shadow-1|2|pop|header`.

### Two jobs, two treatments, never swapped

*Selection* (active nav, tab, selected row, focus ring, open menu item, current
step) is the brand blue: `--select*`. *Readings* (a figure, a status, a
statutory verdict) are navy figures plus the `--state-*` pills and tints:
`--reading*`, `--status-*`. A verdict is never the selection colour, which is
what stops a selected tab being read as a finding. `check_brand.py` enforces
it: no selection colour may equal a state colour, and `--state-base-year` and
`--state-below-min` must stay a stated CIE76 distance apart. (In the modern
theme base year is a sky blue for exactly this reason.)

### Deprecated aliases and the ratchet

`--accent*` (readings), `--accent-2*` (selection) and `--exp-*` (old brand
names) still work, aliasing the roles. `src/lib/tokens.test.js` counts every use
in `src/**/*.css|jsx` and fails if any count **rises**; it also fails if a
count falls without its ceiling being lowered, so a migration and its ratchet
move in the same commit. New code reads the role.

## Themes

`html[data-theme="modern"|"classic"]`, chosen by `VITE_THEME` (default
`modern`) through `brand.config.js` and applied by `applyTheme()` in `main.jsx`
before the first render. A choice stored under `localStorage['tcc-theme']`
outranks the build default (the style guide's toggle, and the dev tools, use
it). Run the gates under either theme with `TCC_THEME=classic`.

## Re-skinning for a customer

Override **semantic roles** in `frontend/src/styles/overlay.css` (imported last,
so it wins at equal specificity). `overlays/<name>/theme.css` is copied over it
before the build, the same step as the logo. Typical overrides: `--font-sans`
(point it back to Roboto), `--select`, `--select-strong`, `--identity-start`,
`--identity-end-strong`, `--overlay-accent`. Do not override the `--state-*`
meanings or the data-register tokens. Tailwind's colour names are bridged to
the same tokens (`--tw-*`), so they follow.

## Type, space and the two density registers

**Chrome and composition** (header, hero, cards, tiles, tabs, pills, stepper,
workspace) use the comfortable scale; **data grids stay dense**.

| Step | Modern | Classic |
| --- | --- | --- |
| `--text-micro` | 12 | 9 |
| `--text-caption` | 12 | 10 |
| `--text-small` | 13 | 11 |
| `--text-body` | 14 | 12 |
| `--text-strong` | 15 | 13 |
| `--text-subhead` | 16 | 14 |
| `--text-title` | 24 | 18 |
| `--text-display` | 32 | 22 |
| `--text-data` | 12 | 12 |

Eight named steps and no half pixel, as before; `--text-data` is the data
register and no theme changes it.

- **The data register.** Table cells, headers, figures and verbatim engine
  output read `--text-data` (12px), 28px rows (`--row-height-data`) and 8px cell
  padding (`--cell-pad-data`). Inside a `table`, a `.trend-block` or a figure
  tile the modern theme collapses the chrome steps onto `--text-data` and sets
  `--font-data` (Roboto), because Poppins runs ~10% wider and the widest grid
  (18 columns) is already close to its holder's width. The dense page header and KPI figures collapse
  `--text-display` onto `--text-title` for the same reason (the visible-row gate).
- **Line height** is a theme token (`--leading-base|heading|dense`): Poppins'
  natural line box is ~28% taller than Roboto's.
- **Raw `px` in `font-size`, `padding`, `margin`, `gap`, `border-radius` and
  `style={{ }}` are bugs.** `--space-1..10` is the dense scale (2, 4, 6, 8, 10,
  12, 14, 16, 20, 24); `--space-11..16` (28, 32, 40, 48, 56, 64) is the chrome tail.
- **12px is the floor for data.** Anything below needs a stated reason.

## Components

`frontend/src/components/ui/`, one implementation of each, token-only CSS next
to the component, one test file each, a header comment saying why it exists and
what it must never do. Import from `components/ui/index.js`.

| Component | Use it for | Never |
| --- | --- | --- |
| `Button` | Every action. `primary` (gradient), `secondary`, `ghost`, `link`, `danger`; `sm`/`md`; `icon`, `loading`, `disabled`; `href` renders a link. | Put a verdict on it, or hand-roll `<button class="btn">`. |
| `Card` | A surface with `title`, `subtitle`, `actions`, an inner `tabs` slot and a `footer`. | Nest a card in a card for spacing. |
| `Pill` | A status or category. Variants are the five `--state-*` families plus `info` and `category`; `soft` or `outline`; optional ✓ ✕ ● so colour is never the only signal. | Take a colour from props, or use brand blue for a verdict. |
| `CountBadge` | A count on an icon or tab (`99+`), full count in `aria-label`. | Show zero by default. |
| `Tabs` | The one tab implementation: `underline` (page, section, card) or `segmented` (an inline choice), count chip, roving tabindex, arrows/Home/End. `MethodTabs`, `GridTabs`, `SectionTabs` are wrappers. | Render a tab outside a tablist. |
| `KpiTile` / `KpiRow` | A tinted tile: a large centred figure over a caption. Tone is a state family. | Tint by topic, compute the value, or show an absent figure at the weight of a real one. |
| `Callout` | An inset assessment card with a status dot and a bold title. | Carry the finding in colour alone. |
| `Stepper` | A route-driven guided flow (`done`, `current`, `upcoming`, `disabled`), `aria-current="step"`. | Block navigation like a wizard. |
| `TaskCard` | A whole-card link: category chip, title, one-line description, chevron. | Intercept modified clicks. |
| `HeroBand` | A page greeting band (compact variant). | Carry a verdict colour. |
| `MetaLine` | `Label: value · Label: value` as a `<dl>`. `PageHeader` has a `meta` slot for it. | Render a pair with no value. |
| `SectionHeading` | `Title (count)`. | |
| `FloatingAction` | A fixed bottom-right pill. | Cover the primary action area (`FLOATING_CLEARANCE_CLASS`). |
| `EmptyState`, `Skeleton` | The sanctioned empty and loading treatments. `EmptyState`'s title is an `h3`; its body says what to do. | Say "no data" without saying why. |
| `VerdictCard` | Where a verdict is stated per programme, year or finding: border = the reading, pill row, title, inset `Callout` for the derivation, body, `Details →`. | Invent a verdict or a derivation sentence. |

`Card` takes `flush` (no body padding, for a dense grid) and a verdict `tone`
(`above-min`, `below-min`, `partial`, `base-year`), which colours the border from
`--state-*`. `Stepper` steps take `to` (a router link) and a `reason` when
disabled. Page-level pieces built from these live beside the views:
`ClientHeader`, `FootprintPanel`, `TrailSteps`.

`StatCard`/`StatRow` and three hand-rolled `kpi-card` markups were replaced by
`KpiTile`/`KpiRow`. The legacy `.pill-*` classes in `index.css` remain in use
and are migrated to `Pill` with the page work that follows (see UI-STATUS.md).

`/__styleguide` (dev only; absent from the production bundle) renders every
component in every variant with a theme toggle, plus the shell compositions (top
bar, the drill trail at each level, hero and task cards).

### The shell (`src/components/shell/`)

| Piece | Job | Never |
| --- | --- | --- |
| `AppShell` | Skip link, one `<header>` (bar + trail), one `<main id="main-content">`. | Render a second `<main>`, or know which routes exist. |
| `TopBar` | Brand, the navigation groups (`navGroups(NAV, …)`), the right-hand cluster. A one-item group is a link. | Decide what is disabled. |
| `NavGroup` | A WAI-ARIA menu button. Arrows/Home/End move and wrap, Escape returns focus, Tab and outside-click close. A disabled item is focusable, `aria-disabled`, with a visible reason. | Keep a closed menu in the DOM, or fire a disabled item. |
| `DrillTrail` | Portfolio → Client → Location → Eligibility → Employee from the route (`lib/drill.js`). Reached = button, current = `aria-current`, unreached = dimmed text with a hint. Collapses to one line at the book. | Render an unreached rung as a disabled button. |
| `ShellActions` | The year scope and the account menu (only when signed in). | Offer an action the platform does not provide. |

`shell.css` reads roles only, so both themes share the structure, and it is held
to the token gate (`check_tokens.py`).

## Page patterns

Four compositions, each built from the `ui/` components and the tokens above.
Nothing here adds a colour, a size or a spacing step.

**Dashboard card grid** (`PortfolioPage`). The page's product is full width:
the book is one `Card` (`flush`, so the grid runs edge to edge) with a `Tabs`
row in its header slot. Beneath it, a two-column grid from 1280px (one column
below) of supporting cards: the footprint map and a `KpiRow` of tiles. Tabs carry
a count taken from the unfiltered rows and write the same filter grammar the
column header writes. A tile's tint is a `--state-*` reading (`lib/bookCards.js`),
never a topic colour. Money is not summed in the browser, so tiles show counts.

**Review header and stepper** (`ClientHeader`, `lib/clientFlow.js`). A back link,
the client as the page's one `h1`, and a `MetaLine` (client, tax year, method,
run, rule pack) on a single compact row via `PageHeader compact`; below it a
`Stepper` of links across the client's views. The stepper is route-driven and
never gates content: the current step comes from the URL, an unavailable step is
disabled with its reason on screen and announced, and a view with no place to go
(Discovery) is omitted, not stubbed.

**Verdict card** (`ui/VerdictCard`). Border = the reading (`--state-*`); a pill
row (what it is about, then the verdict with a glyph so colour is never the only
signal); the title; an inset `Callout` for the derivation sentence, omitted when
the caller has none; a body; `Details →`. A verdict is never the selection blue,
and `check_brand.py` asserts that over the rendered book.

**Data grid.** Header filled `--surface-subtle`, hairline row dividers
`--border-subtle`, the name column `--text-link`, figures navy and tabular, hover
tint, and an open or selected row in the selection language (`--select-bg`, a
`--select` bar on its first cell). 28px rows, 12px text and 8px cell padding are
the data register and do not change. Verdict cells use `Pill`. Sorting and
filtering are behaviour and keep their grammar.

**Calculation trail** (`TrailSteps`). A numbered list of cards; engine output is
verbatim JSON in the data register at 12px or more; a hash chip ties a step to
its source and configuration.

## Third-party assets

The footprint map's state geometry is vendored, not fetched:
`frontend/public/us-states-10m.json`, the `states-10m.json` file from the
[`us-atlas`](https://github.com/topojson/us-atlas) package v3.0.1 (ISC licence,
Copyright 2013-2019 Michael Bostock), which is TopoJSON derived from the US Census
Bureau's cartographic boundary files (public domain). It is referenced as
`${import.meta.env.BASE_URL}us-states-10m.json`. The type is the latin subset of
`@fontsource` Poppins and Roboto (SIL OFL), woff2 only, declared in
`src/styles/fonts.css` (see "Type, fonts and performance"). Nothing is loaded
from a third-party origin, and `check_brand.py` fails on any request that leaves
the origin.

## The Ask workspace

`src/components/ask/` is the one conversation surface (it replaced the slide-in
chat drawer). It is a modal `role="dialog"` titled "Ask Copilot", always mounted
and drawing nothing when closed, so a conversation survives a close.

| Part | What it is |
| --- | --- |
| About header | `MetaLine` (client / tax year / method) and an "Ask about this page" button that sends the page's own prompt |
| Conversation | Plan strip (what the router chose), numbered clarification, composer, suggested prompts, "Need clarification?" footer |
| Evidence pane | The typed `evidence` blocks the answer came from: tables, figures, trails, links, with a count |
| Layout | At 1280px and wider, conversation \| evidence side by side; narrower, tabs "Conversation \| Evidence (n)" |
| Confirm card | The write-flow extension point: a `kind: "confirmation"` item shows what WOULD be recorded and two buttons. Inert today: nothing emits one, and with no `onConfirm` wired the Confirm button is disabled and says so. An expired confirmation cannot be confirmed |

Rules: one launcher (the floating pill, `#ask-launcher`, and the row "Ask"
buttons open the same workspace); Esc closes, Tab is trapped, the page does not
scroll behind it, and focus returns to what opened it; every figure in the
evidence pane is a string rendered verbatim; a block that fails validation is
dropped and counted, never repaired. The contract with the backend is
[ASK-EVIDENCE-CONTRACT.md](ASK-EVIDENCE-CONTRACT.md).

## Type, fonts and performance

`src/styles/fonts.css` declares the faces: Poppins 400/500/600/700 and Roboto
400/500/600/700/800, woff2 only. Not `@fontsource/*/*.css`, because each of those
declares a woff beside every woff2 and the bundle shipped both. Each family also
has a metric-matched fallback face (`Poppins Fallback`, `Roboto Fallback`:
`size-adjust` and the three overrides computed from the font's metrics), listed
after the real family in `--font-sans` / `--font-data`, so `font-display: swap`
shows text at once and the swap does not move the layout. `vite.config.js`
preloads the two faces the first paint uses (Poppins 400, Roboto 400).
`fonts.test.js` guards all of it.

| Measure | Before | After |
| --- | --- | --- |
| Font files in `dist/` | woff + woff2 | **woff2 only**, 138.8 kB |
| Layout shift from the font swap (fonts held 6s) | not measured | 0.001 to 0.002, both themes (gate: 0.10) |
| Built CSS | 165 kB | 125.9 kB (dead rules removed, `tools/dead_css.mjs`) |

## States

Every routed page has to say what it is doing when it cannot show data. The four
states and the components that draw them: **loading** (`Skeleton`, labelled),
**empty** (`EmptyState` for an absence), **error** (`EmptyState`, which says
nothing was changed), and **declined** (a scope the data cannot honour is named
in a "Scope adjusted" banner under the shell, never answered with another
year's figures or a zero). `tools/check_states.py` forces each of them on every
page.

## Accessibility

Semantic landmarks; visible focus (`--focus-ring`); keyboard operation (roving
tabindex on tabs); `aria-current`, `aria-selected`, labelled regions; colour is
never the only signal; text contrast ≥ WCAG AA (4.5:1, or 3:1 for large text and
icons). **Use grey 700 (or darker) for text; grey 600 is for icons and large
type only.** `check_contrast.py` measures the pairs actually rendered.

The gate is `tools/check_a11y.py` (axe-core, pinned): zero violations of impact
serious or critical on every routed page, the styleguide and the open Ask
workspace, in both themes. Classic `color-contrast` is reported, not failed
(D9). What is reported but not gated, so it can be worked down: moderate
`landmark-unique` / `landmark-no-duplicate-banner` on the shell header and
repeated specimen navs, and `heading-order` where a page starts on an `h2`.
Disabled stepper steps carry a dashed marker and a struck label, so "not
available" is not mistaken for "not yet".

## Layout and spacing: the calm pass

The first modern skin changed colours and type and left the shell as it was, and
it showed: a navy slab for a top bar, a navy slab for the rail, tinted stripes,
800-weight uppercase labels, buttons whose icon sat on one line and label on the
next. Measured against the reference renderings (white bar, light band, cards
with generous inner padding and a hairline, one idea per block), the page was
busier, not cleaner. The audit that followed, and what it fixed:

| Finding | Fix |
| --- | --- |
| Icon above label on `Download claim package` and every row `Ask` (Tailwind preflight sets `svg { display: block }`) | `svg.lucide` is inline; any button/link/summary with an `<svg>` child is an inline-flex row. Fixed for both themes. |
| Chips wrapping to two lines (`ONE FILE`) | `white-space: nowrap` on `.pill` and `.cov-scope`; the engagement list is a 3-column grid. |
| Navy top bar and navy rail | White bar and white rail with a hairline; selection is a soft brand-blue tint with a 3px bar. (The rail has since been replaced by a top navigation and a drill trail: D14.) |
| Download button on a row of its own (52px) | It shares the client tabs row. |
| Tight, uneven header block | Eyebrow muted at 600, title 600 navy, sub at 90ch, one 16px gap before the content. |
| Tinted stripes and heavy borders on informational cards | Hairline `--border-subtle`; stripes kept only where they are a verdict. |
| Grey KPI tiles with shouted uppercase labels | Number over a quiet caption on a light tile. |
| Grid-paper page background, shadows at rest | Plain white page, no shadow at rest. |

It lives in `frontend/src/styles/chrome-modern.css`, scoped to the modern theme.
**The acceptance viewport is 1440×900** (desktop only, by owner decision); the
visible-row gate is held at the pre-revamp 7 / 13 / 17 rows at that size.

## Running the gates

```pwsh
python frontend/tools/check_all.py            # the whole table
python frontend/tools/check_all.py --quick    # no unit tests, build or sweep
$env:TCC_THEME='classic'; python frontend/tools/measure_ui.py   # one tool, one theme
python frontend/tools/check_perf.py           # needs `npx vite preview --port 4173` after a build
python frontend/tools/shoot_pages.py after modern   # Visual QA pack, gitignored
python frontend/tools/compare.py before after-modern --diff 2   # contact sheet
```

See [frontend/tools/README.md](../../frontend/tools/README.md) for each check
and for running them on a clone without the private inputs.
