/**
 * The What-if tab's state, carried in the query string.
 *
 * A Reading pill on the location grid opens What-if already scoped to that
 * location, year and method, so the projection starts from the row the reader
 * was looking at. The state is in the URL for the same reason the drill is a
 * route: a pasted link renders the same projection cold.
 *
 * Framework-free, because the rule for WHICH lever a pill pre-fills is a
 * decision someone will want to read and test, not a detail of a click handler.
 */

export const CLIENT_TABS = ['location', 'claimed', 'progress', 'whatif'];
export const DEFAULT_CLIENT_TAB = 'location';

export const LEVER_ACTIONS = ['add_headcount', 'remove_headcount', 'adjust_hours', 'adjust_wages'];
const METHODS = ['min_max', 'pay_period'];

/** Only a year that was MEASURED against a base can be moved — or an open one, still moving. */
const ACTIONABLE = new Set(['above_minimum', 'below_minimum', 'in_progress']);

export function clientTab(search) {
  const tab = search?.get?.('ctab');
  return CLIENT_TABS.includes(tab) ? tab : DEFAULT_CLIENT_TAB;
}

/**
 * Whole jobs a location-year is short of its minimum, or 0 when it clears it.
 *
 * Rounded UP: a projection offered as "hire 1" to a location 1.66 short would
 * leave it below the line, which is the one thing the pre-fill exists to avoid.
 * The epsilon keeps 2.0000001 from becoming three hires.
 */
export function jobsShort(row) {
  const threshold = Number(row?.threshold);
  let netNew = Number(row?.net_new_vs_base);
  // Net new clamps at zero, so a location BELOW its base reads "2 short" when
  // it is 2 plus the whole shortfall. Signed against the base where the row
  // carries it: Cascade GA-016 in TY2026 once sat at 3.0 against 7.33, and two
  // hires would leave it exactly where it was.
  const average = Number(row?.average_headcount);
  const base = Number(row?.base_average_headcount);
  if (row?.average_headcount != null && row?.base_average_headcount != null
    && Number.isFinite(average) && Number.isFinite(base)
    && netNew <= 0.005 && average - base < 0) {
    netNew = average - base;
  }
  if (!Number.isFinite(threshold) || !Number.isFinite(netNew)) return 0;
  const gap = threshold - netNew;
  return gap > 0 ? Math.ceil(gap - 1e-6) : 0;
}

export function isWhatIfTarget(row) {
  return !!row && !row.is_base_year && ACTIONABLE.has(row.status);
}

/**
 * The query-string patch a Reading pill applies, or null for a row that is not
 * a what-if (a base year is the baseline itself; a partial year has no full
 * measurement to move).
 *
 * Below the minimum pre-fills Hire with the jobs short and runs it — the answer
 * to "what would it take" is on screen on arrival. Above the minimum only
 * scopes: there is no single lever that obviously follows from "fine".
 */
export function whatIfLink(row, { unitId, method } = {}) {
  if (!isWhatIfTarget(row) || !unitId) return null;
  // Behind pace in an open year is "what would it take" too, asked while it still can be.
  const behind = row.status === 'below_minimum' || (row.status === 'in_progress' && !row.qualified);
  const short = behind ? jobsShort(row) : 0;
  return {
    ctab: 'whatif',
    wunit: unitId,
    wstack: '',
    wemp: '',
    wyear: String(row.tax_year),
    wmethod: METHODS.includes(method) ? method : 'min_max',
    wlever: short ? 'add_headcount' : '',
    wmag: short ? String(short) : '',
    wrun: short ? '1' : '',
  };
}

/**
 * The What-if STACK (28 Sep): several employees, each working differently for
 * the rest of the year, projected together in one engine run.
 *
 * Carried in the URL as `wstack=token~hours~raise,token~hours~raise`, so a
 * pasted link reproduces the scenario. Record tokens only — an employee id
 * never enters a URL. `~` and digits need no escaping, and a token is hex.
 */
export const MAX_STACK = 25;
const MAX_HOURS = 40;
const MAX_RAISE = 100;

const clamp = (value, max) => {
  const n = Number(value);
  if (!Number.isFinite(n) || n < 0) return 0;
  return Math.min(n, max);
};

/** `wstack` -> `[{ token, hours, raise }]`. Malformed and repeated entries drop out. */
export function parseStack(value) {
  const seen = new Set();
  const out = [];
  for (const part of String(value || '').split(',')) {
    const [token, hours, raise] = part.split('~');
    if (!token || !/^[0-9a-zA-Z]+$/.test(token) || seen.has(token)) continue;
    seen.add(token);
    out.push({ token, hours: clamp(hours, MAX_HOURS), raise: clamp(raise, MAX_RAISE) });
    if (out.length === MAX_STACK) break;
  }
  return out;
}

const trim = (n) => String(Math.round(Number(n) * 100) / 100);

export function formatStack(stack) {
  return (stack || []).map((e) => `${e.token}~${trim(e.hours)}~${trim(e.raise)}`).join(',');
}

/**
 * What one Near-the-line row adds to the stack, or null when there is no rest
 * of the year to change (on pace, closed, hired after the checkpoint).
 *
 * Pre-filled with the pair that closes THAT person's gap: more hours for
 * somebody short on hours, and — where they are paid below the threshold rate
 * — the hours the hours floor needs plus the raise that clears the wage floor.
 */
export function stackEntry(row) {
  const rest = row?.rest_of_year;
  if (!row?.record_token || rest?.state !== 'open') return null;
  return {
    token: row.record_token,
    hours: clamp(rest.suggested_additional_weekly_hours ?? rest.additional_weekly_hours, MAX_HOURS),
    raise: clamp(rest.suggested_hourly_raise ?? 0, MAX_RAISE),
  };
}

/** Add entries, keeping any already there as they are (their edits stand). */
export function addToStack(stack, entries) {
  const out = [...(stack || [])];
  const have = new Set(out.map((e) => e.token));
  for (const entry of entries || []) {
    if (!entry || have.has(entry.token) || out.length >= MAX_STACK) continue;
    have.add(entry.token);
    out.push(entry);
  }
  return out;
}

export function removeFromStack(stack, token) {
  return (stack || []).filter((e) => e.token !== token);
}

/**
 * The query-string patch that puts `stack` in What-if for one year and method.
 * A stack belongs to ONE client-year under one method: its figures were read
 * there. Changing either starts a new one rather than mixing rulers.
 */
export function stackPatch(stack, { taxYear, method, open = false } = {}) {
  return {
    ...(open ? { ctab: 'whatif' } : {}),
    wstack: formatStack(stack),
    wyear: taxYear == null ? '' : String(taxYear),
    wmethod: METHODS.includes(method) ? method : 'min_max',
    wunit: '',
    wemp: '',
    wlever: '',
    wmag: '',
    wrun: open && stack?.length ? '1' : '',
  };
}

/** Everything What-if reads from the URL, validated. */
export function parseWhatIf(search) {
  const get = (key) => search?.get?.(key) || '';
  const year = Number(get('wyear'));
  const magnitude = Number(get('wmag'));
  const action = get('wlever');
  const method = get('wmethod');
  let stack = parseStack(get('wstack'));
  // A link from before the stack (WI-19) named one employee in `wemp`.
  if (!stack.length && get('wemp')) {
    stack = parseStack(`${get('wemp')}~${get('wmag') || 1}~0`);
  }
  return {
    unitId: get('wunit') || null,
    stack,
    year: Number.isInteger(year) && year > 0 ? year : null,
    method: METHODS.includes(method) ? method : 'min_max',
    action: LEVER_ACTIONS.includes(action) ? action : null,
    magnitude: Number.isFinite(magnitude) && get('wmag') !== '' ? magnitude : null,
    autorun: get('wrun') === '1',
  };
}