/**
 * Whether the home page's "Start here" row is open.
 *
 * Remembered per browser, not per account: it is a view preference, and nothing
 * about a client or a calculation is stored under this key. A FIRST visit is
 * expanded, because the cards are how a new reader learns what the product is
 * for; a returning reader who collapsed them gets the fold back, which is the
 * state the visible-row gate measures.
 */
export const START_HERE_KEY = 'tcc.startHere.v1';

export function loadStartHere(storage = globalThis.localStorage) {
  try {
    return storage?.getItem(START_HERE_KEY) !== 'collapsed';
  } catch {
    return true;
  }
}

export function storeStartHere(open, storage = globalThis.localStorage) {
  try {
    storage?.setItem(START_HERE_KEY, open ? 'expanded' : 'collapsed');
  } catch {
    // Storage can be blocked; the preference simply does not persist.
  }
}
