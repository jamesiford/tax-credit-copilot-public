/**
 * Sort and filter for any table small enough to hold in the browser.
 *
 * 29 Sep, James: "make sure that all tables are sortable and filterable" —
 * prompted by Near the line, where the people a location needs could not be
 * lined up by location. The three page grids already had this, each written for
 * its own columns (`gridSort.js` knows the trend grid's). This is the same
 * behaviour for a table that declares its columns:
 *
 *   { key, label, type, read }      — `type` from gridFilter (TEXT, NUMERIC,
 *                                      ENUM, YEAR); `read(row)` the value.
 *   sortable: false / filterable: false to opt a column out.
 *   sortValue(row) when the sort key differs from the filter value.
 *
 * Filtering is `gridFilter.js`, unchanged, so a chip means the same thing on
 * every table. Framework-free, so it tests without a DOM.
 */
import { applyFilters, ENUM, NUMERIC, YEAR } from './gridFilter.js';

/** Missing values sort LAST whichever way the column is ordered. */
function compare(a, b, type) {
  const missingA = a == null || a === '' || (typeof a === 'number' && Number.isNaN(a));
  const missingB = b == null || b === '' || (typeof b === 'number' && Number.isNaN(b));
  if (missingA || missingB) return missingA === missingB ? 0 : (missingA ? 1 : -1);
  if (type === NUMERIC || type === YEAR) return Number(a) - Number(b);
  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: 'base' });
}

function readForSort(column, row) {
  const value = column.sortValue ? column.sortValue(row) : column.read(row);
  if (Array.isArray(value)) return value[0];
  if (column.type === NUMERIC && value != null && value !== '') return Number(value);
  return value;
}

/**
 * Stable multi-key sort. Equal rows keep the order they arrived in, which for
 * a server-ranked list (Near the line, closest first) is the ranking itself.
 */
export function sortBy(rows, keys, columns) {
  const usable = (keys || []).filter((k) => columns[k.key]);
  if (!usable.length) return rows;
  return rows
    .map((row, index) => ({ row, index }))
    .sort((left, right) => {
      for (const { key, desc } of usable) {
        const column = columns[key];
        const a = readForSort(column, left.row);
        const b = readForSort(column, right.row);
        const missing = (a == null || a === '') !== (b == null || b === '');
        const order = compare(a, b, column.type);
        // Missing stays last in both directions: flipping it would put the
        // rows with nothing to say at the top of a descending sort.
        if (order) return missing ? order : (desc ? -order : order);
      }
      return left.index - right.index;
    })
    .map((entry) => entry.row);
}

/** Click: make it the key or flip it. Shift-click: add it as the next key. */
export function toggleKey(current, key, { additive = false } = {}) {
  const existing = (current || []).find((k) => k.key === key);
  if (!additive) return [{ key, desc: existing ? !existing.desc : false }];
  if (!existing) return [...current, { key, desc: false }];
  return current.map((k) => (k.key === key ? { ...k, desc: !k.desc } : k));
}

/** Filter, then sort. The filtered count is what a FilterBar reports. */
export function arrangeRows(rows, columns, { sort = [], filters = {} } = {}) {
  const filterable = Object.fromEntries(
    Object.entries(columns).filter(([, c]) => c.filterable !== false),
  );
  return sortBy(applyFilters(rows || [], filterable, filters), sort, columns);
}

export { ENUM, NUMERIC, YEAR };
