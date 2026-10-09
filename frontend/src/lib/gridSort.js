import { designationCode } from './trendGrid.js';

/**
 * Sorting for the client grid — client-side, because 36 rows is not a query.
 *
 * The unit's employee list is deliberately NOT sorted here: Candle Bottle has
 * 10,236 employees across 101 units, and client-side sorting does not survive
 * that. That one is server-side.
 *
 * Framework-free so it can be unit-tested without a DOM.
 */

/** Columns the grid can sort on, and how each one reads a row. */
export const SORT_KEYS = {
  tax_year: (row) => row.tax_year,
  average_headcount: (row) => Number(row.average_headcount ?? 0),
  total: (row) => Number(row.total ?? 0),
  net_new_vs_base: (row) => Number(row.net_new_vs_base ?? 0),
  status: (row) => String(row.status ?? ''),
  // The code on screen, not the stored sentence, so sort and display agree.
  designation: (row) => designationCode(row),
  annual_credit_usd: (row) => Number(row.annual_credit_usd ?? 0),
};

/**
 * Parse `sort=net_new_vs_base:desc,tax_year:asc` into keys.
 *
 * Multi-key because shift-click adds a second, and an unknown column is
 * dropped rather than throwing — a shared URL from an older build must still
 * render something.
 */
export function parseSort(raw) {
  if (!raw) return [];
  return String(raw)
    .split(',')
    .map((part) => {
      const [key, order] = part.split(':');
      return { key, desc: order === 'desc' };
    })
    .filter((entry) => entry.key in SORT_KEYS);
}

export function formatSort(keys) {
  return keys.map(({ key, desc }) => `${key}:${desc ? 'desc' : 'asc'}`).join(',');
}

/**
 * Click a header: make it the primary key, or flip it if it already is.
 * Shift-click keeps the existing keys and appends, so a second key refines the
 * first rather than replacing it.
 */
export function toggleSort(current, key, { additive = false } = {}) {
  if (!(key in SORT_KEYS)) return current;
  const existing = current.find((entry) => entry.key === key);
  if (!additive) {
    return [{ key, desc: existing ? !existing.desc : false }];
  }
  if (!existing) return [...current, { key, desc: false }];
  return current.map((entry) => (entry.key === key ? { ...entry, desc: !entry.desc } : entry));
}

/** Stable: equal rows keep their original order, so a sort cannot shuffle. */
export function sortRows(rows, keys) {
  if (!keys.length) return rows;
  return rows
    .map((row, index) => ({ row, index }))
    .sort((a, b) => {
      for (const { key, desc } of keys) {
        const read = SORT_KEYS[key];
        const left = read(a.row);
        const right = read(b.row);
        if (left < right) return desc ? 1 : -1;
        if (left > right) return desc ? -1 : 1;
      }
      return a.index - b.index;
    })
    .map((entry) => entry.row);
}

/** Filter unit blocks by a free-text needle over unit id, name and FEIN. */
export function filterBlocks(blocks, needle) {
  const query = String(needle || '').trim().toLowerCase();
  if (!query) return blocks;
  return blocks.filter((block) => (
    String(block.unit_id || '').toLowerCase().includes(query)
    || String(block.name || '').toLowerCase().includes(query)
    || (block.feins || []).some((fein) => String(fein).toLowerCase().includes(query))
  ));
}
