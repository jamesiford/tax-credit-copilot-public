export const NUM = new Intl.NumberFormat('en-US');
export const MONEY = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export const SOURCE_FIELD_MAP = [
  { source: 'TCCEmployeeId', target: 'Employee', use: 'Customer-wide eligibility key' },
  { source: 'Tax Year', target: 'Source tax year', use: 'Retained for lineage; FY dates control selection' },
  { source: 'JobTitle', target: 'Job title', use: 'Authorized source context' },
  { source: 'TCCUnitId', target: 'Unit', use: 'Applied after eligibility, in monthly employment' },
  { source: 'PayPeriodStart', target: 'PPS', use: 'Min-Max span and period coverage' },
  { source: 'PayPeriodEnd', target: 'PPE', use: 'Fiscal selection and period coverage' },
  { source: 'PaycheckDate', target: 'Pay date', use: 'Fiscal-year selection' },
  { source: 'PayFrequency', target: 'Cadence code', use: 'Pay Period denominator' },
  { source: 'FEIN', target: 'Legal entity', use: 'Applied after eligibility, in monthly employment' },
  { source: 'Hours', target: 'Signed hours', use: 'Common employee totals' },
  { source: 'Wages', target: 'Signed wages', use: 'Common employee totals' },
];

export function shortHash(value, size = 12) {
  if (!value) return '—';
  const text = String(value).replace(/^sha256:/, '');
  return `${text.slice(0, size)}…`;
}

export function eligibilityLabel(status) {
  return {
    both: 'Eligible in both',
    min_max_only: 'Min-Max only',
    pay_period_only: 'Pay Period only',
    neither: 'Not eligible',
  }[status] || status || 'Unknown';
}

export function statusTone(status) {
  if (['complete', 'reconciled', 'both', 'approved', 'source_confirmed'].includes(status)) return 'ok';
  if (['awaiting_outputs', 'not_supplied', 'proposed_v1', 'proposed', 'v2_review_required', 'v3_review_required', 'v4_review_required', 'review_required', 'manual_review_required', 'blocked_on_reviewed_cycle_evidence', 'discrepancies', 'min_max_only', 'pay_period_only'].includes(status)) return 'warn';
  return 'neutral';
}

export function monthLabel(isoDate) {
  if (!isoDate) return '—';
  return new Date(`${isoDate}T00:00:00`).toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
}

export function stageLabel(stage) {
  return String(stage || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function assumptionEntries(group) {
  return Object.entries(group?.assumptions || {}).map(([id, value]) => ({ id, ...value }));
}

/**
 * The tax years a programme has authored statute for, as a reader says them.
 * Contiguous runs collapse to a range; a gap is kept, because a missing year is
 * a year we cannot calculate and must not look covered. An empty list returns
 * null so the caller states "no authored years" rather than printing a blank.
 */
export function authoredYearsLabel(years) {
  const sorted = [...new Set((years || []).map(Number).filter(Number.isFinite))].sort((a, b) => a - b);
  if (!sorted.length) return null;
  const runs = [];
  let start = sorted[0];
  let prev = sorted[0];
  for (const year of sorted.slice(1)) {
    if (year === prev + 1) { prev = year; continue; }
    runs.push(start === prev ? String(start) : `${start}\u2013${prev}`);
    start = year; prev = year;
  }
  runs.push(start === prev ? String(start) : `${start}\u2013${prev}`);
  return runs.join(', ');
}
