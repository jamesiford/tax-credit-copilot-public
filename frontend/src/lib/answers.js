/**
 * The sentence each page opens with.
 *
 * Framework-free and unit-tested, because the answer is the most load-bearing
 * thing on the screen: it is what a viewer repeats to somebody else, and it has
 * to be derivable from the payload rather than assembled by eye.
 */

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

const n = (value) => (Number.isFinite(Number(value)) ? Number(value) : 0);
const plural = (count, word) => `${count} ${word}${count === 1 ? '' : 's'}`;

/**
 * Employees at a unit, and the ones a shift short.
 *
 * The cusp count is the actionable figure and cannot come from the qualified
 * list: `onezero_matrix` holds only people already above the floor, so a count
 * taken from it is structurally zero. `near_threshold` is the separate cohort.
 * The BAND is applied here rather than in SQL, and the floor comes from the
 * rule pack the API returned — never a hardcoded 35.
 *
 * A COLUMN FILTER MUST NOT MOVE THIS SENTENCE. It is a claim about the
 * location, not about what the reader has narrowed to, so the count comes from
 * the API's unfiltered total. The band clause is SUPPRESSED rather than
 * restated while a near-threshold filter is in force: a filtered cusp count is
 * a different figure wearing the same words, and suppressing beats misstating.
 */
export function unitAnswer(payload, monthIndex, band = 5) {
  const counted = payload?.total_unfiltered ?? (payload?.employees || []).length;
  const floor = payload?.thresholds?.min_weekly_hours;
  const near = payload?.near_threshold || [];
  const nearNarrowed = Object.keys(payload?.near_filters_applied || {}).length > 0;

  const parts = [plural(counted, 'employee')];
  if (monthIndex != null) parts.push(`${counted} counted in ${MONTHS[monthIndex]}`);

  if (floor != null && !nearNarrowed) {
    const within = near.filter(
      (row) => row.avg_weekly_hours != null && n(row.avg_weekly_hours) >= floor - band,
    );
    if (within.length) {
      parts.push(`${within.length} more within ${band} hrs of the ${floor}-hr floor`);
    }
  }
  return `${parts.join(' · ')}.`;
}

/** Employees at a unit within the band, for a caller that needs the list. */
export function withinBand(payload, band = 5) {
  const floor = payload?.thresholds?.min_weekly_hours;
  if (floor == null) return [];
  return (payload?.near_threshold || []).filter(
    (row) => row.avg_weekly_hours != null && n(row.avg_weekly_hours) >= floor - band,
  );
}

/** Locations, how many qualify, what they are worth, and the base year. */
export function clientAnswer(payload) {
  const items = payload?.items || [];
  const units = new Set(items.map((row) => row.worksite_id));
  // WI-15. "Qualify" is a statement about ONE year, and the strip under this
  // sentence counts each location's latest. Counting any year that ever
  // qualified read "6 qualify" directly above "4 qualify · 2 below".
  const latest = new Map();
  const open = [];
  for (const row of items) {
    // An open year is a forecast, not a qualification. It is said separately.
    if (row.status === 'in_progress') { open.push(row); continue; }
    const seen = latest.get(row.worksite_id);
    if (!seen || row.tax_year > seen.tax_year) latest.set(row.worksite_id, row);
  }
  const latestRows = [...latest.values()];
  const qualifying = latestRows.filter((row) => row.qualified).length;
  const latestYears = [...new Set(latestRows.map((row) => row.tax_year))];
  const inYear = latestYears.length === 1 ? ` in TY${latestYears[0]}` : ' in their latest year';

  const annual = (payload?.unit_totals || [])
    .reduce((total, row) => total + n(row.total_annual_credit_usd), 0);
  const years = [...new Set(
    items.filter((row) => row.status !== 'in_progress').map((row) => row.tax_year),
  )].sort((a, b) => a - b);
  const baseYears = items.filter((row) => row.is_base_year).map((row) => row.tax_year);

  const parts = [plural(units.size, 'location')];
  parts.push(`${qualifying} qualify${inYear}`);
  if (annual > 0) {
    // A sum over every year, so it names the years rather than saying "annual".
    const span = years.length > 1 ? ` across TY${years[0]}–TY${years[years.length - 1]}` : '';
    parts.push(`$${annual.toLocaleString(undefined, { maximumFractionDigits: 0 })} claimable${span}`);
  }
  if (open.length) {
    // At most four figures: the open year's standing outranks the base year,
    // because it is the one a reader can still do something about.
    const onTrack = open.filter((row) => row.qualified).length;
    parts.push(`${onTrack} of ${open.length} on track in TY${open[0].tax_year} so far`);
  } else if (baseYears.length) parts.push(`TY${Math.min(...baseYears)} base`);
  return `${parts.join(' · ')}.`;
}

/**
 * The book, and the single client closest to qualifying.
 *
 * Counts come from the API's own totals, not from the rows on screen: those are
 * one page of a paginated list, so counting them understates the book.
 */
export function portfolioAnswer(summary, nearest) {
  const total = summary?.total_clients;
  const assessed = summary?.assessed_clients;
  if (total == null) return null;

  const parts = [plural(total, 'client')];
  if (assessed != null) parts.push(`${assessed} assessed`);
  // The SIGNED margin. `gap_jobs` clamps at zero, so a client already over the
  // line reads "0.0 jobs from qualifying" — which names the one client on the
  // book who has nothing to do as the one closest to needing something. Being
  // just over and just under are both `on_the_line`, and they are opposite
  // conversations.
  if (nearest?.name && nearest.jobs_margin != null) {
    const margin = n(nearest.jobs_margin);
    parts.push(
      margin < 0
        ? `${Math.abs(margin).toFixed(1)} jobs from qualifying: ${nearest.name}`
        : `${nearest.name} holds the threshold by ${margin.toFixed(1)} jobs`,
    );
  }
  return `${parts.join(' · ')}.`;
}

/** Periods, effort against the floor, and how much of the year was reached. */
export function employeeAnswer(data) {
  if (!data) return null;
  const periods = (data.raw_source_rows || []).length;
  const floor = data.thresholds?.minimum_average_weekly_hours;
  const method = data.step1?.min_max || data.step1?.pay_period;
  const hours = method?.avg_weekly_hours;

  const parts = [plural(periods, 'period')];
  if (hours != null) {
    parts.push(floor != null
      ? `${n(hours).toFixed(1)} avg weekly hrs vs a ${n(floor)}-hr floor`
      : `${n(hours).toFixed(1)} avg weekly hrs`);
  }

  const months = data.onezero?.months || [];
  const rows = data.onezero?.min_max || [];
  if (months.length && rows.length) {
    const reached = months.filter(
      (_, index) => rows.some((row) => n(row.months?.[index]) > 0),
    ).length;
    parts.push(`counted in ${reached} of ${months.length} months`);
  }
  return `${parts.join(' · ')}.`;
}

/**
 * Why a paycheck did not count.
 *
 * `included` is a boolean and cannot say WHICH reason applied. "Outside fiscal
 * window", "shorter than seven days" and "filtered by pay code" are three
 * different findings and a reviewer has to tell them apart — the first is a
 * window question, the second a statutory test, the third a mapping decision.
 */
export function decisionBreakdown(rows) {
  const counts = new Map();
  for (const row of rows || []) {
    const key = row.selection_decision || (row.included ? 'included' : 'excluded');
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return [...counts.entries()]
    .map(([decision, count]) => ({ decision, count }))
    .sort((a, b) => b.count - a.count);
}
