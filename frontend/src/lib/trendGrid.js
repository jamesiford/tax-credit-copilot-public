/**
 * The trend grid: locations down, months across, years stacked.
 *
 * Pure logic only — no React, no fetch. The colour rule in particular lives in
 * exactly one function so that when the partner corrects what green means, it
 * changes in one place rather than in twelve cells and a legend.
 *
 * The spreadsheet this replaces used raw yellow/green/red/cyan. Those map onto
 * the tones the product already owns rather than being reproduced literally:
 * two palettes doing the same job read as two meanings.
 */

export const MONTH_LABELS = ['M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7', 'M8', 'M9', 'M10', 'M11', 'M12'];

/**
 * Which state the grid should ask about.
 *
 * At all-programmes scope the jurisdiction list is alphabetical, and taking its
 * first entry asked for Colorado — a programme with no authored years — for a
 * Georgia client, which 404s. The answer is the first jurisdiction that is both
 * priceable and present in this client's payroll; anything else is a state we
 * cannot answer for.
 */
export function trendState(scope, options, clientScope) {
  const programs = options?.programs || [];

  if (scope?.programCode && scope.programCode !== 'all') {
    const one = programs.find((p) => p.program_code === scope.programCode);
    return one?.jurisdiction?.code || '';
  }

  const priceable = programs.filter(
    (p) => p.calculable && p.jurisdiction?.level === 'state' && p.jurisdiction?.code,
  );
  const clientStates = clientScope?.states || [];
  const inPayroll = priceable.find((p) => clientStates.includes(p.jurisdiction.code));
  return (inPayroll || priceable[0])?.jurisdiction?.code || '';
}

/** The two statutory readings, in the order they are offered. */
export const METHODS = [['min_max', 'Min-Max'], ['pay_period', 'Pay Period']];

/**
 * Backend reading -> tone class -> what a viewer is being told.
 *
 * `base` is deliberately the accent (blue) rather than the spreadsheet's yellow.
 * The base year is not a warning; it is the reference every other row is read
 * against, and amber next to a genuinely amber partial year would collide.
 */
export const STATUS_META = {
  base: { tone: 'accent', label: 'Base year', hint: 'The frozen baseline every later year is measured against.' },
  above_minimum: { tone: 'green', label: 'Above minimum', hint: 'Net-new jobs cleared the minimum for this location.' },
  below_minimum: { tone: 'bad', label: 'Below minimum', hint: 'Net-new jobs fell short of the minimum; nothing claimable this year.' },
  partial: { tone: 'amber', label: 'Partial year', hint: 'Fewer than twelve months of payroll fall inside this window.' },
  no_data: { tone: 'muted', label: 'No payroll', hint: 'This location has no payroll inside the year.' },
  // WI-21. A year before a base the reader chose: not measured, so not a reading.
  before_base: { tone: 'muted', label: 'Before base', hint: 'Before the chosen base year, so not measured against it.' },
  // TY2026. A year still running: read on its closed months, never priced.
  in_progress: { tone: 'muted', label: 'In progress', hint: 'The year is still open: read on its closed months, and nothing is claimable until it closes.' },
};

/**
 * An open year's two readings. Drawn as an OUTLINE, like Declining on the
 * book: "on track" is a forecast about a year nobody has filed, and a filled
 * pill would put it in the same grammar as a verdict on a finished year.
 */
const OPEN_YEAR_META = {
  true: { tone: 'forecast-ok', label: 'On track', hint: 'Year to date, net-new jobs clear the minimum. The year is still open; nothing is claimable until it closes.' },
  false: { tone: 'forecast-bad', label: 'Behind pace', hint: 'Year to date, net-new jobs are short of the minimum. The year is still open, so there is time to close the gap.' },
};

export function statusMeta(status) {
  return STATUS_META[status] || STATUS_META.no_data;
}

/** The reading one ROW states. Same as `statusMeta` except for an open year. */
export function readingMeta(row) {
  if (row?.status === 'in_progress') return OPEN_YEAR_META[Boolean(row.qualified)];
  return statusMeta(row?.status);
}

/** Tone -> the badge class the design system already ships. */
export const PILL_CLASS = {
  accent: 'pill-accent',
  green: 'pill-ok',
  amber: 'pill-warn',
  bad: 'pill-bad',
  muted: 'pill-neutral',
  'forecast-ok': 'pill-forecast-ok',
  'forecast-bad': 'pill-forecast-bad',
};

export function pillClass(tone) {
  return PILL_CLASS[tone] || PILL_CLASS.muted;
}

/**
 * What each designation code means, in a reader's words. The codes are the partner's:
 * "T1, T1, T1B40, T1" is how the golden report reads.
 */
const DESIGNATION_TITLES = {
  T1: 'Tier 1',
  'T1 B40': 'Tier 1 — one of the 40 least developed counties',
  T2: 'Tier 2',
  T3: 'Tier 3',
  T4: 'Tier 4',
  MZ: 'Military zone',
  OZ: 'Opportunity zone',
  LDCT: 'Less developed census tract',
};

/** The code a location-year shows, or 'Unassigned' where none is on record. */
export function designationCode(row) {
  if (!row || row.tier_source === 'unassigned' || (!row.designation && row.tier == null)) {
    return 'Unassigned';
  }
  const code = String(row.designation || '').trim();
  if (DESIGNATION_TITLES[code]) return code;
  // Legacy registry rows carry a sentence ("Tier 1 — Standard"); say the tier.
  return row.tier != null ? `T${row.tier}` : 'Unassigned';
}

/**
 * The hover text: what the code means, and that it is prototype data which
 * the engine does not apply. A designation is shown, not calculated with.
 */
export function designationTitle(row) {
  const code = designationCode(row);
  if (code === 'Unassigned') return 'No designation on record for this location in this year';
  return `${DESIGNATION_TITLES[code] || code} · TY${row.tax_year ?? ''} · prototype designation data (DISC-10); shown, not applied by the engine`;
}

/** The tone for one unit-year row. One rule, one place. */
export function rowTone(row) {
  return readingMeta(row).tone;
}

/**
 * The tone for a single month cell.
 *
 * A month is read against the unit's MINIMUM — its base-year average plus that
 * year's job threshold — rather than against the row's own verdict, so a year
 * that failed overall still shows which months carried it. Green means that
 * month's count would qualify on its own; red means it would not.
 *
 * 30 Sep: this read against the bare base average, so GA-007 painted twelve
 * green months of 21 against a 20.17 base in a year that was BELOW its 22.17
 * minimum. A month above the base but under the minimum is not a month that
 * qualifies, and green said it was.
 *
 * Months with no headcount stay neutral — colouring a zero red says the
 * location shrank when it may simply not have opened yet. `unreachable` is
 * stronger than that: no pay period reaches the measuring date at all, so the
 * zero is a fact about the pay calendar. Colouring it as a decline would invent
 * a finding.
 */
export function monthTone(value, {
  baseMonthlyAverage = 0, threshold = 0, isBaseYear = false, unreachable = false,
} = {}) {
  // A month nothing spans that still COUNTED was counted by the Month-12 rule
  // (the employee's last period end after the 15th). That is the agreed method,
  // so the figure is read like any other month; only a month the rule could
  // not rescue stays neutral, because its zero is a calendar fact.
  if (unreachable && !(value > 0)) return 'muted';
  if (!Number.isFinite(value) || value <= 0) return 'muted';
  if (isBaseYear) return 'accent';
  if (!baseMonthlyAverage) return 'green';
  // Qualifying is net new >= the threshold, so exactly AT the minimum is green.
  const minimum = baseMonthlyAverage + (Number(threshold) || 0);
  return value >= minimum - 1e-9 ? 'green' : 'bad';
}

/** Month positions no pay period reaches, for one tax year. */
export function unreachableFor(payload, taxYear) {
  const meta = (payload?.year_meta || []).find((entry) => entry.tax_year === taxYear);
  return new Set(meta?.unreachable_months || []);
}

/**
 * One sentence per location, derived rather than written.
 *
 * The source spreadsheet carried a hand-typed note per filing group. A model
 * could write a better sentence, but a model must not be the thing that tells
 * an operator a location lost its designation [ADR-004]. This says only what
 * the computed rows already prove.
 */
export function statusSentence(unit) {
  const rows = unit?.rows || [];
  if (!rows.length) return 'No payroll resolved for this location.';

  const evaluated = rows.filter((row) => !row.is_base_year);
  if (!evaluated.length) return 'Base year only — no later year to compare against yet.';

  // An open year is a forecast; "N of M years qualify" counts finished years.
  const closed = evaluated.filter((row) => row.status !== 'in_progress');
  const open = evaluated.find((row) => row.status === 'in_progress');
  const latest = evaluated[evaluated.length - 1];
  const qualifying = closed.filter((row) => row.qualified);
  const parts = [];

  if (latest === open) {
    const months = latest.months_reachable ? ` over ${latest.months_reachable} closed months` : '';
    parts.push(latest.qualified
      ? `On track in ${latest.tax_year}: ${latest.net_new_vs_base.toFixed(1)} net-new${months}, against a ${latest.threshold}-job minimum.`
      : `Behind pace in ${latest.tax_year}: ${latest.net_new_vs_base.toFixed(1)} net-new${months}, against a ${latest.threshold}-job minimum.`);
  } else if (latest.qualified) {
    parts.push(`Above the ${latest.threshold}-job minimum in ${latest.tax_year} on ${latest.net_new_vs_base.toFixed(1)} net-new.`);
  } else if (latest.status === 'partial') {
    parts.push(`${latest.tax_year} is a partial year — ${latest.months_with_headcount} of 12 months.`);
  } else {
    parts.push(`Dipped below the ${latest.threshold}-job minimum in ${latest.tax_year}.`);
  }

  if (evaluated.some((row) => row.backfilled)) {
    const year = evaluated.find((row) => row.backfilled).tax_year;
    parts.push(`Backfilled in ${year}.`);
  }
  if (closed.length) parts.push(`${qualifying.length} of ${closed.length} years qualify.`);
  return parts.join(' ');
}

/** The last FINISHED year in a block's rows — what "qualifies" is said about. */
export function latestClosedRow(rows) {
  const closed = (rows || []).filter((row) => row.status !== 'in_progress');
  return closed.length ? closed[closed.length - 1] : null;
}

/** The open year's row, if the block holds one. */
export function openYearRow(rows) {
  return (rows || []).find((row) => row.status === 'in_progress') || null;
}

/** The years the credit columns span, labelled YR1..YRn off the base year. */
export function creditColumns(unit) {
  const columns = unit?.credit_years || [];
  return columns.map((column, index) => ({
    ...column,
    label: `YR${index + 1}`,
  }));
}

/** Headcount reads as a whole person when it is one, and a fraction when it is not. */
export function fmtHeadcount(value) {
  if (!Number.isFinite(value)) return '—';
  if (value === 0) return '—';
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

/**
 * Who is behind one cell.
 *
 * The matrix is one row per (employee, unit, segment), so an employee can appear
 * more than once at the same location — deduped by employee id, because the
 * drawer answers "who was counted", not "how many segments were there".
 * `monthIndex` of null asks for the whole year.
 */
export function contributorsFrom(matrix, unitId, monthIndex) {
  const seen = new Map();

  for (const item of matrix?.matrix || []) {
    if (item.unit_id !== unitId) continue;
    const counted = monthIndex == null
      ? (item.months || []).reduce((sum, value) => sum + value, 0)
      : (item.months || [])[monthIndex];
    if (!counted) continue;
    const existing = seen.get(item.employee_id);
    seen.set(item.employee_id, {
      record_token: item.record_token,
      employee_id: item.employee_id,
      counted: existing ? existing.counted + counted : counted,
    });
  }

  return [...seen.values()].sort((a, b) => a.employee_id.localeCompare(b.employee_id));
}

/**
 * Shape the payload into what the grid renders.
 *
 * Sorted by what needs attention: locations that dipped below the minimum in
 * their latest year first, then locations that qualify, then everything else.
 * A grid ordered by unit id makes the operator find the problem themselves.
 */
export function buildBlocks(payload) {
  const units = payload?.units || [];

  return units
    .map((unit) => {
      const rows = unit.rows || [];
      const baseRow = rows.find((row) => row.is_base_year) || null;
      const latest = rows.length ? rows[rows.length - 1] : null;
      return {
        ...unit,
        rows,
        baseRow,
        latest,
        baseMonthlyAverage: baseRow ? baseRow.average_headcount : 0,
        sentence: statusSentence(unit),
        credits: creditColumns(unit),
        attention: latest && !latest.is_base_year && !latest.qualified,
      };
    })
    .sort((a, b) => {
      if (a.attention !== b.attention) return a.attention ? -1 : 1;
      const delta = (b.total_annual_credit_usd || 0) - (a.total_annual_credit_usd || 0);
      return delta || a.unit_id.localeCompare(b.unit_id);
    });
}

// --- WI-21 base-year picker ------------------------------------------------

/**
 * Chosen bases live in the URL (`rebase=GA_GA-010:2022,GA_GA-013:2021`), so a
 * pasted link shows the same re-priced blocks. An entry that does not parse is
 * dropped rather than guessed at.
 */
export function parseRebase(value) {
  const out = {};
  for (const part of String(value || '').split(',')) {
    const at = part.lastIndexOf(':');
    if (at <= 0) continue;
    const unit = part.slice(0, at);
    const year = Number(part.slice(at + 1));
    if (unit && Number.isInteger(year) && year > 0) out[unit] = year;
  }
  return out;
}

export function formatRebase(map) {
  return Object.entries(map || {})
    .filter(([, year]) => year != null)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([unit, year]) => `${unit}:${year}`)
    .join(',');
}

/**
 * Years that can be a base: complete ones. A partial year is a flattering
 * base, and an open one has not finished — its closed months look complete.
 */
export function baseYearChoices(block) {
  return (block?.rows || [])
    .filter((row) => row.status !== 'in_progress')
    .filter((row) => Number(row.months_with_headcount || 0) >= Number(row.months_reachable || 12))
    .map((row) => row.tax_year)
    .sort((a, b) => a - b);
}

/**
 * A block re-priced against a chosen base, from the rebase read. Every figure
 * comes from that read; this only puts it where the grid already looks.
 */
export function rebaseBlock(block, rebase) {
  if (!block || !rebase || rebase.worksite_id !== block.unit_id) return block;
  const byYear = new Map(rebase.years.map((y) => [y.tax_year, y]));
  const rows = block.rows.map((row) => {
    const next = byYear.get(row.tax_year);
    if (!next) return row;
    return {
      ...row,
      status: next.status,
      is_base_year: next.role === 'base',
      before_base: next.role === 'before_base',
      year_number: next.year_number ?? null,
      qualified: Boolean(next.qualified),
      backfilled: Boolean(next.backfilled),
      net_new_vs_base: next.role === 'evaluated' ? Number(next.net_new_vs_base) : 0,
      annual_credit_usd: next.annual_credit_usd ?? 0,
    };
  });
  const baseRow = rows.find((row) => row.is_base_year) || null;
  const latest = rows.length ? rows[rows.length - 1] : null;
  return {
    ...block,
    rows,
    baseRow,
    latest,
    base_year: rebase.base_year,
    baseMonthlyAverage: baseRow ? baseRow.average_headcount : 0,
    total_annual_credit_usd: rebase.total_annual_credit_usd,
    attention: Boolean(latest && !latest.is_base_year && !latest.qualified),
    rebased: {
      base_year: rebase.base_year,
      inferred_base_year: rebase.inferred_base_year,
      delta_annual_credit_usd: rebase.delta_annual_credit_usd,
      run_total_annual_credit_usd: rebase.run_total_annual_credit_usd,
    },
  };
}

/** The roll-up strip above the grid. Counts, never a re-derivation of dollars. */
export function summariseTrend(payload, blocks) {
  const years = payload?.years || [];
  // "Qualify" is said about a FINISHED year; an open one is on track or not.
  const qualifyingLocations = blocks.filter((block) => latestClosedRow(block.rows)?.qualified).length;
  const open = blocks.map((block) => openYearRow(block.rows)).filter(Boolean);

  return {
    locations: blocks.length,
    years: years.length,
    yearRange: years.length ? `TY${years[0]}–TY${years[years.length - 1]}` : '—',
    qualifyingLocations,
    openYear: open.length ? open[0].tax_year : null,
    openLocations: open.length,
    onTrackLocations: open.filter((row) => row.qualified).length,
    attentionLocations: blocks.filter((block) => {
      const closed = latestClosedRow(block.rows);
      return closed && !closed.is_base_year && !closed.qualified;
    }).length,
    annualCreditUsd: payload?.totals?.annual_credit_usd || 0,
    lifetimeUsd: payload?.totals?.tranche_lifetime_usd || 0,
    declinedYears: payload?.declined_years || [],
  };
}
