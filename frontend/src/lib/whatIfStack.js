/**
 * The What-if stack, held across pages (29 Sep).
 *
 * The stack was a query string on the client page, so it existed only there.
 * James wanted to add people from a location's near-the-floor list and from an
 * employee's walk as well — pages with their own URLs — so the stack needs a
 * home those pages share:
 *
 * - **Membership** (record token, +hrs/wk, +$/hr) plus its client, year and
 *   method, kept in `sessionStorage`. Tokens and numbers only: an employee id
 *   never leaves the page it was shown on, and a reload keeps the stack.
 * - **Who each person is** (id, location, pay), kept in MEMORY only, from the
 *   row they were added from. It names them in the stack table without writing
 *   an employee id anywhere; after a reload the projection names them instead.
 *
 * The client page's URL stays the source of truth while it is open (a pasted
 * link reproduces a stack); it reads this store when it opens without one, and
 * writes to it whenever its own changes.
 *
 * Framework-free apart from storage, which is injectable for tests.
 */
import { addToStack, removeFromStack, stackEntry } from './whatIf.js';

const KEY = 'tcc.whatif.stack';
const people = new Map();
const listeners = new Set();

let storage = typeof window !== 'undefined' ? window.sessionStorage : null;

/** For tests: swap the storage backend (anything with getItem/setItem/removeItem). */
export function setStackStorage(next) {
  storage = next;
}

const clean = (stack) => (stack && Array.isArray(stack.entries) ? stack : null);

/** The stack for one client, year and method, or an empty one. */
export function readStack({ clientId, taxYear, method = 'min_max' } = {}) {
  const saved = readSavedStack();
  const same = saved
    && String(saved.clientId) === String(clientId)
    && Number(saved.taxYear) === Number(taxYear)
    && (saved.method || 'min_max') === method;
  return same ? saved.entries : [];
}

/** Whatever stack is saved, with its client, year and method; or null. */
export function readSavedStack() {
  try { return clean(JSON.parse(storage?.getItem(KEY) || 'null')); } catch { return null; }
}

/** Replace the stack. An empty one clears it. */
export function writeStack({ clientId, taxYear, method = 'min_max' }, entries) {
  try {
    if (!entries?.length) storage?.removeItem(KEY);
    else storage?.setItem(KEY, JSON.stringify({ clientId, taxYear, method, entries }));
  } catch { /* private mode: the stack lives for this page only */ }
  listeners.forEach((fn) => fn());
}

/**
 * Add rows (Near the line, near-the-floor, the walk). A stack for another
 * client, year or method is replaced rather than mixed: its figures were read
 * under a different ruler. Returns how many were added.
 */
export function addRows(scope, rows) {
  const current = readStack(scope);
  const entries = (rows || []).map(stackEntry).filter(Boolean);
  const next = addToStack(current, entries);
  (rows || []).forEach(rememberPerson);
  writeStack(scope, next);
  return next.length - current.length;
}

export function removeToken(scope, token) {
  writeStack(scope, removeFromStack(readStack(scope), token));
}

/** Remember who a token is, for the stack table. In memory only. */
export function rememberPerson(row) {
  if (row?.record_token) people.set(row.record_token, row);
}

export function personFor(token) {
  return people.get(token) || null;
}

export function knownPeople() {
  return Object.fromEntries(people);
}

/** Re-render when the stack changes elsewhere on this page. */
export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
