/**
 * Column filters, as one grammar both ends of the wire agree on.
 *
 * The client grid filters 36 rows in the browser; the unit grid pushes the same
 * expression into SQL against 10,236 employees. Writing the grammar twice is
 * how a control ends up meaning one thing on screen and another in the query,
 * so it is written once here and parsed once in `api/_gridfilter.py`.
 *
 * Wire form: `col:expr;col:expr`
 *
 *   text     `employee_id:~ABC`      contains, case-insensitive
 *   numeric  `avg_weekly_hours:>=35` comparator, or `weeks_worked:10..52`
 *   enum     `status:qualified|declined`  multi-select
 *   year     `tax_year:2023|2024`         multi-select
 *
 * A filter that does not parse is DROPPED rather than passed through, so it
 * cannot show up as an active chip while matching everything. A control that
 * looks live and filters nothing is how a reader trusts a wrong total.
 *
 * Framework-free, so it tests without a DOM.
 */

export const TEXT = 'text';
export const NUMERIC = 'numeric';
export const ENUM = 'enum';
export const YEAR = 'year';

/** Longest first: `>=` must win over `>`. */
const COMPARATORS = ['>=', '<=', '>', '<', '='];

/**
 * A number, or null. `Number(null)` is 0 and `Number('')` is 0, so the naive
 * form makes an absent value compare as zero — which puts every employee with
 * no recorded hours at the top of a "below 5 hours" filter.
 */
const num = (value) => {
  if (value == null || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

/**
 * `>=35` · `10..52` · `35`.
 *
 * A bare number reads as `>=` because every numeric column here answers an
 * "at least" question, and an exact match on a two-decimal average matches
 * nothing. The controls always write the operator, so only a hand-typed URL
 * ever takes that branch.
 */
export function parseNumeric(expr) {
  const raw = String(expr ?? '').trim();
  if (!raw) return null;
  const range = raw.match(/^(-?\d+(?:\.\d+)?)\.\.(-?\d+(?:\.\d+)?)$/);
  if (range) {
    const a = Number(range[1]);
    const b = Number(range[2]);
    return { op: '..', min: Math.min(a, b), max: Math.max(a, b) };
  }
  for (const op of COMPARATORS) {
    if (raw.startsWith(op)) {
      const value = num(raw.slice(op.length));
      return value == null ? null : { op, value };
    }
  }
  const bare = num(raw);
  return bare == null ? null : { op: '>=', value: bare };
}

/** Normalise one raw expression against its column type, or null if unusable. */
export function parseFilter(spec, raw) {
  const text = String(raw ?? '').trim();
  if (!spec || !text) return null;
  if (spec.type === NUMERIC) {
    const parsed = parseNumeric(text);
    return parsed && { type: NUMERIC, ...parsed };
  }
  if (spec.type === ENUM || spec.type === YEAR) {
    const values = text.split('|').map((v) => v.trim()).filter(Boolean);
    return values.length ? { type: spec.type, values } : null;
  }
  const needle = text.startsWith('~') ? text.slice(1).trim() : text;
  return needle ? { type: TEXT, needle: needle.toLowerCase() } : null;
}

export function matchesFilter(row, spec, parsed) {
  if (!parsed) return true;
  const value = spec.read(row);
  if (parsed.type === TEXT) {
    return String(value ?? '').toLowerCase().includes(parsed.needle);
  }
  if (parsed.type === ENUM || parsed.type === YEAR) {
    // A cell may legitimately hold SEVERAL values — a client operates in more
    // than one state — and then the row matches if any of them is selected.
    // Expressed as a property of the column rather than a new operator, so the
    // written grammar stays `col:a|b` everywhere it appears.
    if (spec.multi) {
      const held = Array.isArray(value) ? value : [value];
      return held.some((v) => parsed.values.includes(String(v ?? '')));
    }
    return parsed.values.includes(String(value ?? ''));
  }
  const n = num(value);
  if (n == null) return false;
  if (parsed.op === '..') return n >= parsed.min && n <= parsed.max;
  if (parsed.op === '>=') return n >= parsed.value;
  if (parsed.op === '<=') return n <= parsed.value;
  if (parsed.op === '>') return n > parsed.value;
  if (parsed.op === '<') return n < parsed.value;
  return n === parsed.value;
}

/** Distinct values ACTUALLY PRESENT, so an enum control cannot offer a dead option. */
export function presentValues(rows, read) {
  const seen = new Set();
  for (const row of rows || []) {
    const value = read(row);
    for (const one of Array.isArray(value) ? value : [value]) {
      if (one == null || one === '') continue;
      seen.add(String(one));
    }
  }
  return [...seen].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
}

/** `{ status: 'qualified|declined' }` over a spec map. Unparseable keys drop out. */
export function activeFilters(specs, raw) {
  const out = {};
  for (const [key, expr] of Object.entries(raw || {})) {
    const spec = specs[key];
    if (spec && parseFilter(spec, expr)) out[key] = String(expr).trim();
  }
  return out;
}

export function applyFilters(rows, specs, raw) {
  const parsed = Object.entries(raw || {})
    .map(([key, expr]) => [specs[key], parseFilter(specs[key], expr)])
    .filter(([spec, filter]) => spec && filter);
  if (!parsed.length) return rows;
  return rows.filter((row) => parsed.every(([spec, filter]) => matchesFilter(row, spec, filter)));
}

/** `col:expr;col:expr` → `{ col: 'expr' }`, keeping only columns the grid knows. */
export function parseFilters(specs, wire) {
  const out = {};
  for (const part of String(wire || '').split(';')) {
    const at = part.indexOf(':');
    if (at < 1) continue;
    const key = part.slice(0, at).trim();
    const expr = part.slice(at + 1).trim();
    if (specs[key] && parseFilter(specs[key], expr)) out[key] = expr;
  }
  return out;
}

export function formatFilters(raw) {
  return Object.entries(raw || {})
    .filter(([, expr]) => String(expr ?? '').trim())
    .map(([key, expr]) => `${key}:${String(expr).trim()}`)
    .join(';');
}

/** What a chip says. Reads from the PARSED filter, so it cannot describe a dropped one. */
export function describeFilter(spec, expr) {
  const parsed = parseFilter(spec, expr);
  if (!parsed) return null;
  if (parsed.type === TEXT) return `${spec.label} contains “${parsed.needle}”`;
  if (parsed.type === ENUM || parsed.type === YEAR) {
    const shown = parsed.values.map((v) => (spec.format ? spec.format(v) : v));
    return `${spec.label}: ${shown.join(', ')}`;
  }
  if (parsed.op === '..') return `${spec.label} ${parsed.min}–${parsed.max}`;
  return `${spec.label} ${parsed.op} ${parsed.value}`;
}

/** "12 of 37" — a filtered grid must always say what it is hiding. */
export function hidingLabel(shown, total) {
  return shown === total ? `${total}` : `${shown} of ${total}`;
}
