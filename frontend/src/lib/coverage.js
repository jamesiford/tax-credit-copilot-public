/**
 * Reading a coverage cell.
 *
 * The Position view renders `client x program x year`, and a cell is a
 * **variance, not a status**: the question is what was claimed against what we
 * compute they were entitled to, and the sign decides whether it is revenue or
 * exposure.
 *
 * Which forces two rules that are easy to break by accident:
 *
 * 1. **Opportunity and exposure never net.** They are separate totals all the
 *    way up. A netted headline would let one client's over-claim cancel
 *    another's recoverable dollars — arithmetically true and commercially
 *    useless.
 * 2. **Unverified and certified never render alike.** A client's onboarding
 *    assertion and a state-confirmed filing are identical as a dollar figure
 *    and are not remotely the same claim.
 *
 * The backend already computes `outcome`, `variance_usd` and `opportunity_usd`
 * per cell — nothing here recalculates them. This module is presentation:
 * grouping, ordering, and how a cell should look.
 */

/** How each outcome reads. Order matters: it is the sort priority. */
export const OUTCOME_META = {
  over_claimed: { label: 'Over-claimed', tone: 'exposure', rank: 0, actionable: true },
  under_claimed: { label: 'Under-claimed', tone: 'opportunity', rank: 1, actionable: true },
  unclaimed: { label: 'Unclaimed', tone: 'opportunity', rank: 2, actionable: true },
  confirmed: { label: 'Confirmed', tone: 'settled', rank: 3, actionable: false },
  correctly_not_claimed: { label: 'Nothing to claim', tone: 'settled', rank: 4, actionable: false },
  not_assessed: { label: 'Not assessed', tone: 'unknown', rank: 5, actionable: false },
  out_of_scope: { label: 'Not our mandate', tone: 'muted', rank: 6, actionable: false },
  // Ranks below every comparison: there is nothing here to act on, and sitting
  // among the exposures is what made a baseline read as a finding.
  base_year: { label: 'Baseline year', tone: 'muted', rank: 7, actionable: false },
};

/**
 * Why the earliest year held shows no net-new.
 *
 * True for a client with six years looking at their first, and for a client
 * with only one year. Never names a client: it is a property of the payroll
 * held, not of who they are.
 */
export const BASE_YEAR_NOTE =
  'The earliest year held is the baseline later years are measured against, '
  + 'so it shows no net-new by definition — not because nothing was earned.';

/** Does this cell carry a comparison at all? */
export function isBaseYear(cell) {
  return Boolean(cell && (cell.is_base_year || cell.outcome === 'base_year'));
}

export function outcomeMeta(outcome) {
  return OUTCOME_META[outcome] || { label: outcome || 'unknown', tone: 'unknown', rank: 9, actionable: false };
}

const num = (value) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
};

export const USD = new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD', maximumFractionDigits: 0,
});

/** Compact for grid cells, where a full figure would not fit. */
export function money(value) {
  const n = num(value);
  if (n === 0) return '—';
  const abs = Math.abs(n);
  const sign = n < 0 ? '-' : '';
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${sign}$${Math.round(abs / 1_000)}k`;
  return `${sign}$${Math.round(abs)}`;
}

/**
 * A cell's headline figure, and what that figure means.
 *
 * Deliberately returns the SIGNED variance for an exposure rather than an
 * absolute: a grid that showed "$40k" identically for money owed and money at
 * risk would be actively misleading.
 */
export function cellReading(cell) {
  if (!cell) return { outcome: 'not_assessed', ...outcomeMeta('not_assessed'), amount: 0, verified: true };
  const meta = outcomeMeta(cell.outcome);
  const variance = num(cell.variance_usd);
  const baseYear = isBaseYear(cell);
  return {
    outcome: cell.outcome,
    ...meta,
    // A baseline carries no comparison, so it has no headline figure either.
    amount: baseYear ? 0 : (meta.tone === 'exposure' ? variance : num(cell.opportunity_usd)),
    baseYear,
    identified: num(cell.identified_usd),
    claimed: num(cell.claimed_usd),
    verified: cell.provenance_verified !== false,
    provenance: cell.provenance,
    status: cell.status,
  };
}

/**
 * Index cells by `program x year` for the account-scope grid.
 *
 * Returns `{ programs, years, at(program, year) }`. Years come from the scope
 * window rather than only from the cells, so a year we can price but have not
 * assessed renders as an empty column instead of vanishing — a missing column
 * looks like a year that does not exist.
 */
export function buildGrid(cells, { years = [], programs = [] } = {}) {
  // Defensive: a caller can hand this the wrong shape mid-transition — a
  // portfolio payload has `clients`, an account payload has `cells` — and a
  // library function should not be the thing that takes the page down.
  const rows = Array.isArray(cells) ? cells : [];
  const byKey = new Map();
  rows.forEach((c) => byKey.set(`${c.program_code}:${c.tax_year}`, c));

  const programCodes = programs.length
    ? [...programs]
    : [...new Set(rows.map((c) => c.program_code))].sort();

  const yearList = years.length
    ? [...years].sort((a, b) => a - b)
    : [...new Set(rows.map((c) => c.tax_year))].sort((a, b) => a - b);

  return {
    programs: programCodes,
    years: yearList,
    at: (program, year) => byKey.get(`${program}:${year}`) || null,
  };
}

/** Per-program totals down the row of a grid. */
/**
 * Order clients for the portfolio matrix.
 *
 * Exposure first, then opportunity. Not by dollar value alone: an exposure is a
 * thing we have discovered and cannot un-know, and burying it below a larger
 * opportunity would be exactly the presentational choice this product must not
 * make.
 */
export function rankClients(clients) {
  return [...clients].sort((a, b) => {
    const aExp = num(a.totals?.exposure_usd);
    const bExp = num(b.totals?.exposure_usd);
    if ((aExp > 0) !== (bExp > 0)) return aExp > 0 ? -1 : 1;
    if (aExp !== bExp) return bExp - aExp;
    return num(b.totals?.opportunity_usd) - num(a.totals?.opportunity_usd);
  });
}

/**
 * Every client in the book, not only those with a claim on file.
 *
 * `GET /api/claims/coverage` groups by client FROM CLAIMS, so a client nobody
 * has assessed yet is absent — indistinguishable from one that does not exist.
 * Under a heading reading "what every client claims", that absence asserts a
 * complete book, which is the one thing it is not. The unassessed are appended
 * rather than ranked: they carry no exposure and no opportunity, so ranking
 * them against clients that do would imply we had looked and found nothing.
 */
export function withUnassessedClients(clients, book) {
  const present = new Set((clients || []).map((c) => c.client_id));
  const missing = (book || [])
    .filter((c) => !present.has(c.account_id))
    .map((c) => ({
      client_id: c.account_id, name: c.name, cells: [], totals: null, unassessed: true,
    }))
    .sort((a, b) => String(a.name ?? a.client_id).localeCompare(String(b.name ?? b.client_id)));
  return [...rankClients(clients || []), ...missing];
}

/**
 * The one-line reading of a whole scope.
 *
 * Returns opportunity and exposure separately, plus how much of the grid is
 * actually assessed — a headline figure over a mostly-unassessed grid is a
 * different claim from the same figure over a complete one, and saying so is
 * cheaper than being asked.
 */
export function summarise(totals, { cells = 0 } = {}) {
  const opportunity = num(totals?.opportunity_usd);
  const exposure = num(totals?.exposure_usd);
  const known = num(totals?.cells) || cells;
  return {
    opportunity,
    exposure,
    hasExposure: exposure > 0,
    unverified: num(totals?.unverified_cells),
    exposureCells: num(totals?.exposure_cells),
    cells: known,
  };
}
