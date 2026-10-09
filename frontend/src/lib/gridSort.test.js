import { describe, expect, it } from 'vitest';
import {
  filterBlocks, formatSort, parseSort, sortRows, toggleSort,
} from './gridSort.js';

const rows = [
  { tax_year: 2020, average_headcount: 18.33, net_new_vs_base: 0, status: 'base' },
  { tax_year: 2021, average_headcount: 25.5, net_new_vs_base: 7.17, status: 'above' },
  { tax_year: 2022, average_headcount: 26.17, net_new_vs_base: 7.84, status: 'above' },
];

describe('the sort is drivable from the URL', () => {
  it('round-trips through the query string', () => {
    const keys = parseSort('net_new_vs_base:desc,tax_year:asc');
    expect(keys).toEqual([
      { key: 'net_new_vs_base', desc: true },
      { key: 'tax_year', desc: false },
    ]);
    expect(formatSort(keys)).toBe('net_new_vs_base:desc,tax_year:asc');
  });

  it('drops a column it does not know rather than throwing', () => {
    // A link shared from an older build must still render something.
    expect(parseSort('not_a_column:desc,tax_year:asc')).toEqual([{ key: 'tax_year', desc: false }]);
  });

  it('treats an empty query string as unsorted', () => {
    expect(parseSort('')).toEqual([]);
    expect(parseSort(undefined)).toEqual([]);
  });
});

describe('clicking a header', () => {
  it('makes the column primary, then flips it', () => {
    let keys = toggleSort([], 'average_headcount');
    expect(keys).toEqual([{ key: 'average_headcount', desc: false }]);
    keys = toggleSort(keys, 'average_headcount');
    expect(keys).toEqual([{ key: 'average_headcount', desc: true }]);
  });

  it('replaces the key unless the click is additive', () => {
    const keys = toggleSort([{ key: 'tax_year', desc: false }], 'status');
    expect(keys).toEqual([{ key: 'status', desc: false }]);
  });

  it('shift-click adds a second key rather than replacing the first', () => {
    const keys = toggleSort([{ key: 'status', desc: false }], 'tax_year', { additive: true });
    expect(keys).toEqual([
      { key: 'status', desc: false },
      { key: 'tax_year', desc: false },
    ]);
  });

  it('ignores a column that cannot be sorted', () => {
    const current = [{ key: 'tax_year', desc: false }];
    expect(toggleSort(current, 'decline_reason')).toBe(current);
  });
});

describe('sorting rows', () => {
  it('orders by the primary key', () => {
    const sorted = sortRows(rows, [{ key: 'average_headcount', desc: true }]);
    expect(sorted.map((r) => r.tax_year)).toEqual([2022, 2021, 2020]);
  });

  it('falls to the second key when the first ties', () => {
    const sorted = sortRows(rows, [
      { key: 'status', desc: false },
      { key: 'tax_year', desc: true },
    ]);
    // 'above' sorts before 'base'; within 'above', the later year first.
    expect(sorted.map((r) => r.tax_year)).toEqual([2022, 2021, 2020]);
  });

  it('is stable, so equal rows keep their original order', () => {
    const tied = [{ tax_year: 1, status: 'x' }, { tax_year: 2, status: 'x' }];
    expect(sortRows(tied, [{ key: 'status', desc: false }]).map((r) => r.tax_year))
      .toEqual([1, 2]);
  });

  it('returns the rows untouched when nothing is sorted', () => {
    expect(sortRows(rows, [])).toBe(rows);
  });
});

describe('filtering units', () => {
  const blocks = [
    { unit_id: 'GA_GA-001', name: 'Atlanta Store', feins: ['58-1234567'] },
    { unit_id: 'GA_GA-010', name: 'Macon Operations', feins: ['58-7654321'] },
  ];

  it('matches on unit id, name or FEIN', () => {
    expect(filterBlocks(blocks, 'macon').map((b) => b.unit_id)).toEqual(['GA_GA-010']);
    expect(filterBlocks(blocks, 'GA-001').map((b) => b.unit_id)).toEqual(['GA_GA-001']);
    expect(filterBlocks(blocks, '58-7654321').map((b) => b.unit_id)).toEqual(['GA_GA-010']);
  });

  it('is case-insensitive and ignores surrounding space', () => {
    expect(filterBlocks(blocks, '  ATLANTA ').map((b) => b.unit_id)).toEqual(['GA_GA-001']);
  });

  it('returns everything for an empty needle', () => {
    expect(filterBlocks(blocks, '')).toBe(blocks);
  });
});
