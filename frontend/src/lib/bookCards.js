import { BANDS, band } from './priority.js';

/**
 * What the book's cards say, derived from the rows the endpoint already
 * returned. Counts of clients only: dollars are never re-summed in the browser
 * (a claim is client-grain, and a money total belongs to the warehouse).
 */

//: A band's `tone` is the legacy vocabulary the grid's chips use; a tile reads
//: the --state-* family it means. `forecast` is a projection about a year
//: nobody has filed, so it takes the amber reading, never the red one.
const TILE_TONE = {
  good: 'above-min',
  warn: 'partial',
  forecast: 'partial',
  bad: 'below-min',
  neutral: 'neutral',
};

export function tileTone(bandId) {
  return TILE_TONE[band(bandId).tone] ?? 'neutral';
}

const ORDER = Object.keys(BANDS).sort((a, b) => BANDS[a].rank - BANDS[b].rank);

/** Clients per band, in ranking order, bands nobody is in left out. */
export function bandCounts(rows) {
  const counts = new Map();
  for (const row of rows || []) {
    const id = row.priority_band;
    if (id) counts.set(id, (counts.get(id) || 0) + 1);
  }
  return ORDER.filter((id) => counts.has(id)).map((id) => ({ id, count: counts.get(id) }));
}

/**
 * Tabs over the book: the complete population first, then one per band that
 * has anyone in it. Every tab carries its count, taken from the UNFILTERED
 * rows, so a filter narrows the list and never the tab.
 */
export function bookTabs(rows) {
  return [
    { id: 'all', label: 'All clients', count: (rows || []).length },
    ...bandCounts(rows).map(({ id, count }) => ({
      id, label: band(id).label, count, hint: band(id).line,
    })),
  ];
}

/** The tab a `band:` filter expression selects, or `null` for a custom mix. */
export function activeBookTab(filters) {
  const expr = String(filters?.band || '').trim();
  if (!expr) return 'all';
  return BANDS[expr] ? expr : null;
}

/** The filter the tab writes: the same `band:` term the column header writes. */
export function filtersForTab(filters, tabId) {
  const next = { ...(filters || {}) };
  if (tabId === 'all') delete next.band;
  else next.band = tabId;
  return next;
}

/**
 * Every state anyone in the book operates in, and every one we can price.
 *
 * Union rather than per-client, because the map is the filter for the whole
 * book, and a state nobody operates in is not on it at all. Clients per state,
 * deliberately NOT dollars: a claim is client-grain and a client operates in
 * several states, so a per-state money figure would double-count or credit a
 * state that did not earn it.
 */
export function footprintOf(rows) {
  const clients = new Map();
  const priced = new Set();
  for (const row of rows || []) {
    for (const s of row.states || []) clients.set(s, (clients.get(s) || 0) + 1);
    for (const s of row.priceable_states || []) priced.add(s);
  }
  const held = [...clients.keys()].sort();
  return {
    held,
    priced: [...priced].sort(),
    rows: held.map((code) => ({ code, clients: clients.get(code), priceable: priced.has(code) })),
  };
}

/** The states a `state:` filter expression selects. */
export function selectedStates(filters) {
  return String(filters?.state || '').split('|').map((s) => s.trim()).filter(Boolean);
}
