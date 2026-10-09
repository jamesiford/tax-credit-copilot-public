import { describe, expect, it } from 'vitest';
import { ENUM, NUMERIC, TEXT } from './gridFilter.js';
import { arrangeRows, sortBy, toggleKey } from './tableSort.js';

const COLUMNS = {
  name: { key: 'name', label: 'Name', type: TEXT, read: (r) => r.name },
  hours: { key: 'hours', label: 'Hours', type: NUMERIC, read: (r) => r.hours },
  site: {
    key: 'site', label: 'Location', type: ENUM, multi: true,
    read: (r) => r.sites, sortValue: (r) => r.sites[0],
  },
};

const ROWS = [
  { name: 'E10', hours: 34.5, sites: ['GA_GA-013'] },
  { name: 'E2', hours: null, sites: ['GA_GA-001'] },
  { name: 'E3', hours: 31.2, sites: ['GA_GA-001', 'GA_GA-013'] },
  { name: 'E1', hours: 34.5, sites: ['GA_GA-010'] },
];

const names = (rows) => rows.map((r) => r.name);

describe('sorting any table', () => {
  it('sorts numbers as numbers and text naturally', () => {
    expect(names(sortBy(ROWS, [{ key: 'hours', desc: true }], COLUMNS))).toEqual(['E10', 'E1', 'E3', 'E2']);
    expect(names(sortBy(ROWS, [{ key: 'name', desc: false }], COLUMNS))).toEqual(['E1', 'E2', 'E3', 'E10']);
  });

  it('keeps a missing value last whichever way the column runs', () => {
    expect(names(sortBy(ROWS, [{ key: 'hours', desc: false }], COLUMNS)).at(-1)).toBe('E2');
    expect(names(sortBy(ROWS, [{ key: 'hours', desc: true }], COLUMNS)).at(-1)).toBe('E2');
  });

  it('is stable, so equal rows keep the order the server ranked them in', () => {
    // E10 and E1 tie on 34.5; E10 arrived first and stays first.
    expect(names(sortBy(ROWS, [{ key: 'hours', desc: true }], COLUMNS)).slice(0, 2)).toEqual(['E10', 'E1']);
  });

  it('sorts by location on the site shown, and a second key breaks the tie', () => {
    const keys = [{ key: 'site', desc: false }, { key: 'hours', desc: true }];
    expect(names(sortBy(ROWS, keys, COLUMNS))).toEqual(['E3', 'E2', 'E1', 'E10']);
  });

  it('a click flips the key; shift-click adds the next', () => {
    expect(toggleKey([], 'hours')).toEqual([{ key: 'hours', desc: false }]);
    expect(toggleKey([{ key: 'hours', desc: false }], 'hours')).toEqual([{ key: 'hours', desc: true }]);
    expect(toggleKey([{ key: 'hours', desc: false }], 'site', { additive: true }))
      .toEqual([{ key: 'hours', desc: false }, { key: 'site', desc: false }]);
  });
});

describe('filtering any table', () => {
  it('filters a location on every site a person works at, then sorts', () => {
    const shown = arrangeRows(ROWS, COLUMNS, {
      filters: { site: 'GA_GA-013' }, sort: [{ key: 'hours', desc: true }],
    });
    expect(names(shown)).toEqual(['E10', 'E3']);
  });

  it('ignores a column that opted out of filtering', () => {
    const cols = { ...COLUMNS, hours: { ...COLUMNS.hours, filterable: false } };
    expect(arrangeRows(ROWS, cols, { filters: { hours: '>=40' } })).toHaveLength(4);
  });
});
