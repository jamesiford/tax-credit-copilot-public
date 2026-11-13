/**
 * Run batches: the pure logic behind selecting clients, previewing a batch and reading its progress.
 *
 * Framework-free on purpose (lib/ holds derivation, components hold markup). Nothing here computes a statutory
 * figure; every count it shows is one the API returned. The rule that decides most of the wording: **the preview
 * never promises a skip.** Whether a client is unchanged is decided when its item starts, so the preview states an
 * upper bound and says so.
 */

export const KINDS = [
  { id: 'calculate', label: 'Calculate', hint: 'Run the calculation and write Gold; records the claim for that year.' },
  { id: 'assess', label: 'Assess', hint: 'Record claims only. Writes no calculation.' },
  { id: 'assess_and_calculate', label: 'Both', hint: 'Run the calculation and record claims for every year.' },
];

export const TERMINAL = new Set(['succeeded', 'partial', 'failed', 'cancelled']);
export const isFinished = (batch) => TERMINAL.has(batch?.status);

// ---------------------------------------------------------------- selection

/** A selection is explicit ids, or "everything matching a filter" which the SERVER resolves. */
export const emptySelection = () => ({ ids: [], matching: null });

/** How many clients are selected, or null when "all matching" is a server group whose size is only known at preview. */
export const selectionCount = (sel) => (sel.matching ? sel.matching.count : sel.ids.length);

const plural = (n) => `${n} client${n === 1 ? '' : 's'}`;

/** The selection in words, for the bar and the dialog title. */
export function selectionLabel(sel) {
  const n = selectionCount(sel);
  if (sel.matching) return n == null ? 'All clients matching the filters' : `All ${plural(n)} matching`;
  return `${plural(n)} selected`;
}

export const runLabel = (sel) => {
  const n = selectionCount(sel);
  return n == null ? 'Run for the matching clients' : `Run for ${plural(n)}`;
};

export function toggleId(sel, id) {
  // Picking one row after "select all matching" narrows to explicit ids: the server group no longer describes it.
  const base = sel.matching ? [] : sel.ids;
  const has = base.includes(id);
  return { ids: has ? base.filter((x) => x !== id) : [...base, id], matching: null };
}

export function setPage(sel, pageIds, on) {
  const base = sel.matching ? [] : sel.ids;
  const rest = base.filter((id) => !pageIds.includes(id));
  return { ids: on ? [...rest, ...pageIds] : rest, matching: null };
}

export const pageState = (sel, pageIds) => {
  if (sel.matching) return pageIds.length ? 'all' : 'none';
  const picked = pageIds.filter((id) => sel.ids.includes(id)).length;
  if (!picked) return 'none';
  return picked === pageIds.length ? 'all' : 'some';
};

export const isSelected = (sel, id) => Boolean(sel.matching) || sel.ids.includes(id);

/**
 * The server filter equivalent to the book's column filters, or why there is none.
 *
 * The book filters in the browser over the rows it loaded, so "all N matching" can only be handed to the server when
 * the same narrowing can be written in the server's vocabulary (band, state, program). Anything else (a client-name
 * search, a year or money range) has no server equivalent, and sending a looser filter would run clients the person
 * did not see, so it is refused with the reason rather than approximated.
 */
export function serverFilter(filters = {}) {
  const out = {};
  for (const [key, expr] of Object.entries(filters)) {
    if (!expr) continue;
    const values = String(expr).split('|').filter(Boolean);
    if (['band', 'state', 'program'].includes(key) && values.length === 1) out[key] = values[0];
    else return { ok: false, reason: `The ${key} filter cannot be handed to the server. Select rows instead, or narrow by one band, state or program.` };
  }
  return { ok: true, filter: out };
}

export function scopeFor(sel) {
  if (sel.matching) {
    const f = sel.matching.filter;
    return Object.keys(f).length ? { kind: 'filter', filter: f } : { kind: 'all' };
  }
  return { kind: sel.ids.length === 1 ? 'one' : 'list', client_ids: sel.ids };
}

// ---------------------------------------------------------------- the request

export function startBody({
  selection, kind = 'calculate', programCode = null, taxYears = [], force = false, skipUnchanged = false, refreshOnce = true,
  idempotencyKey = null, confirmItems = null, dryRun = false,
}) {
  return {
    kind,
    scope: scopeFor(selection),
    ...(programCode ? { program_code: programCode } : {}),
    tax_years: taxYears,
    force,
    skip_unchanged: skipUnchanged,
    refresh_once: refreshOnce,
    ...(idempotencyKey ? { idempotency_key: idempotencyKey } : {}),
    ...(confirmItems != null ? { confirm_items: confirmItems } : {}),
    dry_run: dryRun,
  };
}

/** One key per opened dialog, so a double click is the same request and a second dialog is a new one. */
export function newIdempotencyKey() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `k-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export const parseYears = (text) => String(text || '')
  .split(/[ ,]+/).map((s) => s.trim()).filter(Boolean).map(Number).filter((n) => Number.isInteger(n));

// ---------------------------------------------------------------- the preview, in words

const COVERAGE_NOTE = {
  all_years: 'Every earlier run recorded a fingerprint of all the client\u2019s authored-year payroll, so a restated prior year is caught.',
  mixed: 'Some earlier runs do not record a client-wide data fingerprint yet; those clients will run.',
};

/** Skipping is opt-in: say plainly when nothing is skipped, and when earlier runs cannot support a skip yet. */
function skipLines(p) {
  if (p.force) return ['Re-run is forced: every client will run.'];
  if (!p.skip_unchanged) return ['Nothing is skipped: every run starts.'];
  if (['cannot_tell_yet', 'none_yet'].includes(p.skip_coverage)) {
    return ['Skipping is on, but earlier runs do not record a client-wide data fingerprint yet, so nothing can be skipped this time.'];
  }
  const lines = COVERAGE_NOTE[p.skip_coverage] ? [COVERAGE_NOTE[p.skip_coverage]] : [];
  if (p.skip_candidates_upper_bound != null) {
    lines.unshift(`Up to ${p.skip_candidates_upper_bound} may be skipped as unchanged. That is an upper bound: it is decided when each run starts, by comparing the data, the assumptions and the rule pack with the last run.`);
  } else {
    lines.unshift(`Skips as unchanged are decided when each run starts. This preview read the last runs of the first ${p.manifests_read_for} clients only, so it gives no upper bound for the whole selection.`);
  }
  return lines;
}

/** One item is one client and program: say so when a client runs for several. */
function programLines(p) {
  const names = Object.keys(p.programs || {}).filter((k) => k !== 'none');
  if (!p.multi_program_clients && names.length < 2) return [];
  return [`Programs: ${names.map((k) => `${k} (${p.programs[k]})`).join(', ')}. ${p.multi_program_clients} client${p.multi_program_clients === 1 ? ' is' : 's are'} run for more than one program.`];
}

/** The sentences the dialog shows. Every figure is the API's; none is derived here. */
export function previewLines(p) {
  if (!p) return [];
  const lines = [];
  lines.push(`${p.clients} client${p.clients === 1 ? '' : 's'}, ${p.items} run${p.items === 1 ? '' : 's'} to queue.`);
  lines.push(Array.isArray(p.years)
    ? `Tax years: ${p.years.map((y) => `TY${y}`).join(', ')}.`
    : 'Tax year: each client\u2019s latest runnable year, chosen when its run starts.');
  if (p.never_run) lines.push(`${p.never_run} ha${p.never_run === 1 ? 's' : 've'} never been calculated, so ${p.never_run === 1 ? 'it' : 'they'} will run.`);
  lines.push(...programLines(p));
  lines.push(...skipLines(p));
  return lines;
}

export const refreshOnceNote = (refreshOnce) => (refreshOnce
  ? 'One run per client refreshes every year of its payroll, so each client runs once.'
  : 'One run per client and year. Each of those runs refreshes every year, so the cost is multiplied by the number of years.');

export const allClientsNote = (scope) => (scope?.kind === 'all'
  ? 'This is every client in the book. Check the counts before you start it.'
  : null);

export function confirmationOk(preview, typed) {
  if (!preview?.requires_confirmation) return true;
  return String(typed).trim() === String(preview.items);
}

// ---------------------------------------------------------------- a batch in progress

export function progressPct(batch) {
  const total = batch?.progress?.total || 0;
  return total ? Math.round((100 * (batch.progress.done || 0)) / total) : 0;
}

export const STATUS_PILL = {
  queued: 'neutral', running: 'info', succeeded: 'above-min', partial: 'partial', failed: 'below-min', cancelled: 'neutral',
  leased: 'info', skipped_unchanged: 'category', skipped_no_payroll: 'category',
};
export const STATUS_LABEL = {
  queued: 'Queued', running: 'Running', succeeded: 'Succeeded', partial: 'Partly done', failed: 'Failed', cancelled: 'Cancelled',
  leased: 'Starting', skipped_unchanged: 'Skipped: unchanged', skipped_no_payroll: 'Skipped: no data',
};

/** What to do about a failure, by the dependency that caused it (the wording matches RUN-ORCHESTRATION.md). */
export const REMEDY = {
  operational_store: 'The store was unreachable. Check the connection, then retry the failed items.',
  source_lakehouse: 'The payroll source was unreachable. Check the connection, then retry the failed items.',
  source_sql: 'The payroll source was unreachable. Check the connection, then retry the failed items.',
  claims_store: 'The claim store was unreachable. Check the connection, then retry the failed items.',
  conflict: 'A write conflict persisted. Ask the operator to lower the worker concurrency, then retry.',
  validation: 'The request or the client is ambiguous (for example several programmes). Name the programme and start again.',
  worker: 'The worker stopped before finishing. Retry the failed items.',
  internal: 'A bug. The log has the detail; report it.',
};

export function remedyFor(dependency) {
  if (!dependency) return null;
  if (REMEDY[dependency]) return REMEDY[dependency];
  if (dependency.startsWith('lookup:')) return `Author the missing ${dependency.slice(7).replace(/_/g, ' ')}, then retry. It is not retried automatically.`;
  return 'See the item message. Retry once the cause is fixed.';
}

/** Failed items grouped by dependency, largest group first, each with its remedy. */
export function failureGroups(items = []) {
  const groups = new Map();
  for (const item of items) {
    if (item.status !== 'failed') continue;
    const key = item.error_dependency || 'unknown';
    const group = groups.get(key) || { dependency: key, items: [], remedy: remedyFor(item.error_dependency) };
    group.items.push(item);
    groups.set(key, group);
  }
  return [...groups.values()].sort((a, b) => b.items.length - a.items.length);
}

export function durationSeconds(item) {
  if (!item?.started_at || !item?.finished_at) return null;
  return Math.max(0, Math.round((Date.parse(item.finished_at) - Date.parse(item.started_at)) / 1000));
}

export const scopeSummary = (batch) => {
  const spec = batch?.scope_spec || {};
  const n = spec.client_count ?? batch?.counts?.total ?? 0;
  if (batch?.scope_kind === 'all') return `All clients (${n})`;
  if (batch?.scope_kind === 'filter') {
    const f = Object.entries(spec.filter || {}).map(([k, v]) => `${k}: ${v}`).join(', ');
    return `${n} matching ${f || 'the filter'}`;
  }
  return `${n} selected client${n === 1 ? '' : 's'}`;
};
