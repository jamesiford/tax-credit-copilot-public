/**
 * Program manager: the words, the workflow steps and the small pure helpers the Programs pages share. [F05]
 *
 * Nothing here computes a statutory figure and nothing says a value is verified: a draft is a proposal and the portal labels
 * every number "not verified" until a person verifies it against the primary source (ADR-005). The wording is constants so a
 * screen cannot soften it.
 */

export const NOT_VERIFIED = 'Not verified';
export const STATUTE_WARNING = 'Statute values are unverified until a person verifies each one against the primary source. '
  + 'A pack that validates is well-formed, not legally correct.';
export const PREVIEW_LABEL = 'Preview, not verified, not for filing';

export const LIFECYCLE_LABEL = {
  calculable: 'Calculable', described: 'Described, not calculable', draft: 'Draft', retired: 'Retired',
};
export const LIFECYCLE_PILL = {
  calculable: 'above-min', described: 'category', draft: 'partial', retired: 'neutral',
};

export const DRAFT_STATUS_LABEL = {
  draft: 'Draft', validating: 'Validating', needs_changes: 'Needs changes', ready_for_review: 'Ready for review',
  approved_for_export: 'Approved for export', exported: 'Exported', withdrawn: 'Withdrawn',
};
export const DRAFT_STATUS_PILL = {
  draft: 'neutral', validating: 'info', needs_changes: 'below-min', ready_for_review: 'info',
  approved_for_export: 'above-min', exported: 'above-min', withdrawn: 'neutral',
};

export const lifecycleLabel = (row) => LIFECYCLE_LABEL[row?.lifecycle] || row?.lifecycle || '—';

/** `[2019, 2020, 2021, 2023]` as `2019–2021, 2023`. */
export function yearsLabel(years) {
  const sorted = [...(years || [])].sort((a, b) => a - b);
  if (!sorted.length) return 'none authored';
  const runs = [];
  for (const y of sorted) {
    const last = runs[runs.length - 1];
    if (last && y === last[1] + 1) last[1] = y; else runs.push([y, y]);
  }
  return runs.map(([a, b]) => (a === b ? String(a) : `${a}\u2013${b}`)).join(', ');
}

/** What the catalog says about verification: always "Not verified", with how many authored years are still flagged. */
export function unverifiedLabel(row) {
  const flagged = (row?.unverified_years || []).length;
  const authored = (row?.authored_years || []).length;
  if (!authored) return NOT_VERIFIED;
  return flagged ? `${NOT_VERIFIED}: ${flagged} of ${authored} year${authored === 1 ? '' : 's'} flagged` : `${NOT_VERIFIED}: no year flagged in the pack`;
}

export function engagementLabel(engagement) {
  if (!engagement) return 'Unavailable';
  if (!engagement.clients) return 'No clients';
  return `${engagement.clients} client${engagement.clients === 1 ? '' : 's'} (${engagement.in_scope} in scope)`;
}

/** The programs already registered for a state, so the first step can say what the new one sits beside. */
export const programsInStateOf = (rows, state) => {
  const wanted = String(state || '').trim().toUpperCase();
  return wanted ? (rows || []).filter((p) => String(p.state || '').toUpperCase() === wanted) : [];
};

// --- the guided workflow ------------------------------------------------------------------------------------------

export const STEPS = [
  { id: 'basics', label: 'Basics' },
  { id: 'pack', label: 'Program pack' },
  { id: 'years', label: 'Year packs' },
  { id: 'preview', label: 'Preview' },
  { id: 'review', label: 'Review' },
  { id: 'export', label: 'Export' },
];

const hasYears = (draft) => Object.keys(draft?.documents?.years || {}).length > 0;

/** Each step's availability and the reason when it is not available: a disabled step says why, never silently. */
export function stepStates(draft, current) {
  const gates = {
    basics: null,
    pack: draft ? null : 'Create the draft in the first step',
    years: draft ? null : 'Create the draft in the first step',
    preview: !draft ? 'Create the draft in the first step' : hasYears(draft) ? null : 'Add a tax year first: a preview prices a year pack',
    review: draft ? null : 'Create the draft in the first step',
    export: ['approved_for_export', 'exported'].includes(draft?.status) ? null : 'Export needs an approved review',
  };
  const order = STEPS.map((s) => s.id);
  return STEPS.map((step) => {
    const reason = gates[step.id];
    const status = reason ? 'disabled' : step.id === current ? 'current' : order.indexOf(step.id) < order.indexOf(current) ? 'done' : 'upcoming';
    return { ...step, status, reason: reason || undefined };
  });
}

// --- structured editing -------------------------------------------------------------------------------------------

/** The supported model (a flat per-job credit over a One/Zero headcount) as fields; anything else needs the JSON editor. */
export const PACK_FIELDS = [
  { path: 'credit.name', label: 'Credit name', type: 'text' },
  { path: 'credit.statutory_citation', label: 'Statute citation', type: 'text', cite: true, help: 'The statute this credit comes from. Required.' },
  { path: 'jurisdiction.name', label: 'Jurisdiction name', type: 'text' },
  { path: 'filing.window', label: 'Filing window', type: 'text' },
  { path: 'filing.cycle', label: 'Filing cycle', type: 'select', options: ['annual', 'quarterly', 'pre-application', 'per-hire'] },
  { path: 'tax_year_convention.label', label: 'Tax year is labelled by the year it', type: 'select', options: ['begins', 'ends'] },
  { path: 'thresholds.minimum_new_jobs', label: 'Minimum new jobs', type: 'number', number: true },
  { path: 'benefit.amount_per_qualifying_job_usd', label: 'Credit per qualifying job (USD)', type: 'number', number: true },
  { path: 'benefit.benefit_period_years', label: 'Benefit period (years)', type: 'number', number: true },
  { path: 'benefit.carryforward_years', label: 'Carryforward (years)', type: 'number', number: true },
  { path: 'one_zero.min_weekly_hours', label: 'Minimum weekly hours', type: 'number', number: true },
  { path: 'one_zero.min_weekly_wages', label: 'Minimum weekly wages (USD)', type: 'number', number: true },
];

/** A year pack carries the same statutory fields (complete and not inherited) plus where its values came from. */
export const YEAR_FIELDS = [
  { path: '_year_provenance.source', label: 'Source for this year', type: 'text', cite: true, help: 'The primary source this year\u2019s values come from. Required for every number.' },
  ...PACK_FIELDS.filter((f) => f.path !== 'credit.statutory_citation'),
];

export const getIn = (doc, path) => path.split('.').reduce((node, key) => (node == null ? undefined : node[key]), doc);

/** An immutable set: the document is never mutated, so a stale render cannot see a half-edited pack. */
export function setIn(doc, path, value) {
  const [head, ...rest] = path.split('.');
  const next = { ...(doc || {}) };
  next[head] = rest.length ? setIn(next[head] && typeof next[head] === 'object' ? next[head] : {}, rest.join('.'), value) : value;
  return next;
}

/** Field text to a stored value: numbers become numbers, an empty field becomes `null` (never a plausible guess). */
export function coerce(field, raw) {
  const text = String(raw ?? '').trim();
  if (!text) return null;
  if (!field.number) return text;
  const value = Number(text);
  return Number.isFinite(value) ? value : text;
}

/** A year pack skeleton: identity only, every statutory value null and flagged. Nothing is copied from another year (ADR-005). */
export function yearSkeleton(pack, year) {
  const credit = pack?.credit || {};
  const flag = { _prototype_verify: true };
  return {
    _prototype_verification: 'DRAFT skeleton. No value here is verified.',
    rule_pack_version: `0.0.1+ty${year}`,
    jurisdiction: { ...(pack?.jurisdiction || {}) },
    credit: { code: credit.code, name: credit.name, statutory_citation: 'TODO: fill from a cited source; not verified' },
    tax_year_convention: { label: null, regulation: null, ...flag },
    filing: { window: 'TODO: fill from a cited source; not verified', cycle: 'annual', ...flag },
    thresholds: { minimum_new_jobs: null, ...flag },
    benefit: { amount_per_qualifying_job_usd: null, benefit_period_years: null, carryforward_years: null, currency: 'USD', ...flag },
    one_zero: {
      min_weekly_hours: null, min_weekly_wages: null, wage_basis: 'regular', geographic_granularity: 'statewide', pt_aggregation: false,
      headcount_unit_field: 'Worksite_ID', entity_combination: 'permitted', ...flag, wage_floor_basis: { source_tax_year: null, annualized_wage_usd: null, ...flag },
    },
    tax_year: Number(year),
    _year_provenance: { source: 'TODO: fill from a cited source; not verified', adr: 'ADR-005' },
  };
}

/** Parse the advanced editor's text: an object, or the reason it is not one. */
export function parseDocument(text) {
  try {
    const value = JSON.parse(text);
    if (value === null || typeof value !== 'object' || Array.isArray(value)) return { ok: false, error: 'A pack is a JSON object.' };
    return { ok: true, value };
  } catch (reason) {
    return { ok: false, error: `Not valid JSON: ${String(reason.message || reason)}` };
  }
}

// --- validation findings ------------------------------------------------------------------------------------------

/** The validator's paths use `/`; the fields here use `.`. */
export const slashPath = (path) => String(path).replaceAll('.', '/');

export const findingsFor = (validation, file) => (validation?.findings || []).filter((f) => f.file === file);

/** The first error at a field (a dotted path), else the first warning there; the field shows it beside itself. */
export function fieldFinding(validation, file, path) {
  const wanted = slashPath(path);
  const here = findingsFor(validation, file).filter((f) => f.path === wanted && f.severity !== 'info');
  return here.find((f) => f.severity === 'error') || here[0] || null;
}

export function validationSummary(validation) {
  if (!validation) return 'Not validated yet';
  if (validation.valid) return `Valid: well-formed, with ${validation.infos} unverified flag${validation.infos === 1 ? '' : 's'} (valid is not verified)`;
  return `${validation.errors} error${validation.errors === 1 ? '' : 's'} to fix`;
}

/** The validation file labels for the side panel, in the order a person works. */
export const fileLabel = (file) => (file === 'pack' ? 'Program pack' : file === 'draft' ? 'Draft' : file.replace('year ', 'Year '));

export const NEXT_STEPS = [
  'A qualified person, who is neither the author nor the reviewer, verifies every statutory value against the primary source.',
  'Put the files in the repository at the paths in the bundle and add the registry entry from registry-patch.json.',
  'Add the tests and the changelog line listed in COMMIT-CHECKLIST.md; run the gates.',
  'Commit, review and deploy the normal way. The program becomes calculable only when the deployed rules folder holds its year packs.',
];

/** The reason the document cannot be saved yet, or null. */
export const saveBlocked = (draft) => (draft && !['draft', 'needs_changes'].includes(draft.status)
  ? `A draft that is ${DRAFT_STATUS_LABEL[draft.status]?.toLowerCase() || draft.status} cannot be edited` : null);
