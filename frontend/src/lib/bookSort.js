/**
 * Sorting for the book — SERVER-side, single key.
 *
 * Different from `gridSort.js` on purpose. That one sorts 36 rows in the
 * browser and supports a second key, because the whole dataset is already on
 * the page. The book asks `/api/v2/portfolio` to order it, so the sort has to
 * be something the endpoint can express: one key, one direction.
 *
 * The header control is shared (`SortHeader`), the grammar is not. Pretending
 * shift-click works here would offer a second key the server will ignore.
 *
 * Framework-free so it can be unit-tested without a DOM.
 */

//: Columns the endpoint can order by, mapped to the alias it understands.
//: `program` is deliberately absent — `_portfolio_sort_key` has no alias for
//: it, and a header that silently does nothing is worse than no header.
//: `opportunity` is absent because the COLUMN is: it is `identified − claimed`,
//: and no client here has a verified filing to net off.
export const BOOK_SORT_KEYS = {
  band: 'priority',
  year: 'tax_year',
  identified: 'identified_usd',
};

//: What the page falls back to, and what it returns to when a sort is cleared.
export const DEFAULT_BOOK_SORT = { key: 'band', desc: false };

/**
 * Parse `bsort=identified:desc`.
 *
 * An unknown column falls back to the default rather than throwing: a URL
 * shared from an older build must still render the book, and rendering it in
 * the ranking the page was designed around is the safest thing it can do.
 */
export function parseBookSort(raw) {
  if (!raw) return { ...DEFAULT_BOOK_SORT };
  const [key, order] = String(raw).split(':');
  if (!(key in BOOK_SORT_KEYS)) return { ...DEFAULT_BOOK_SORT };
  return { key, desc: order === 'desc' };
}

export function formatBookSort(sort) {
  if (!sort || sort.key === DEFAULT_BOOK_SORT.key) {
    // The default is expressed by ABSENCE, so a clean URL is the ranked one.
    return sort && sort.desc ? `${sort.key}:desc` : '';
  }
  return `${sort.key}:${sort.desc ? 'desc' : 'asc'}`;
}

/**
 * Click a header: flip it if it is already the key, otherwise take it.
 *
 * A money column opens DESCENDING. "Focus resources where the greatest
 * financial impact exists" means largest first, and making somebody click
 * twice to get there is a worse default than picking the useful one.
 */
export function toggleBookSort(current, key) {
  if (!(key in BOOK_SORT_KEYS)) return current;
  if (current?.key === key) return { key, desc: !current.desc };
  return { key, desc: key === 'identified' };
}

/** What `/api/v2/portfolio` should be asked for. */
export function bookSortQuery(sort) {
  return {
    sort: BOOK_SORT_KEYS[sort?.key] || 'priority',
    order: sort?.desc ? 'desc' : 'asc',
  };
}

/**
 * Whether the band ranking has been set aside.
 *
 * The page SAYS this rather than letting the reader notice. Clicking a dollar
 * header silently discards the ordering the whole book was designed around —
 * a client one hire from a threshold is worth $0 today, the same $0 as one
 * fifty hires short, so a value sort buries exactly the client worth ringing.
 * That is a legitimate thing to ask for and an illegitimate thing to hide.
 */
export function ranksByValue(sort) {
  return sort?.key === 'identified';
}
