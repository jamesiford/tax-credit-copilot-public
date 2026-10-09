import { describe, expect, it } from 'vitest';
import {
  DEFAULT_BOOK_SORT, bookSortQuery, formatBookSort, parseBookSort, ranksByValue, toggleBookSort,
} from './bookSort.js';

describe('the book sort', () => {
  it('falls back to the band ranking rather than throwing on an unknown column', () => {
    // A URL shared from an older build must still render the book, and
    // rendering it in the ranking it was designed around is the safest thing
    // it can do.
    expect(parseBookSort('nonsense:desc')).toEqual(DEFAULT_BOOK_SORT);
    expect(parseBookSort('')).toEqual(DEFAULT_BOOK_SORT);
    expect(parseBookSort(null)).toEqual(DEFAULT_BOOK_SORT);
  });

  it('expresses the default by absence, so a clean URL is the ranked one', () => {
    expect(formatBookSort({ key: 'band', desc: false })).toBe('');
    expect(formatBookSort({ key: 'identified', desc: true })).toBe('identified:desc');
  });

  it('round-trips', () => {
    const sort = { key: 'identified', desc: true };
    expect(parseBookSort(formatBookSort(sort))).toEqual(sort);
  });

  it('opens a money column largest first', () => {
    // "Focus resources where the greatest financial impact exists" means
    // largest first. Making somebody click twice to get there is a worse
    // default than picking the useful one.
    expect(toggleBookSort(DEFAULT_BOOK_SORT, 'identified')).toEqual({ key: 'identified', desc: true });
    // A year is not money, so it opens ascending like any ordinary column.
    expect(toggleBookSort(DEFAULT_BOOK_SORT, 'year')).toEqual({ key: 'year', desc: false });
  });

  it('cannot sort by a figure derived from an unverified claim', () => {
    // Recoverable is `identified - claimed`. The column is gone because the
    // subtraction is arithmetic on somebody's assertion; the sort key goes
    // with it rather than staying as reachable API surface.
    expect(toggleBookSort(DEFAULT_BOOK_SORT, 'opportunity')).toEqual(DEFAULT_BOOK_SORT);
    expect(parseBookSort('opportunity:desc')).toEqual(DEFAULT_BOOK_SORT);
  });

  it('flips a column that is already the key', () => {
    const first = toggleBookSort(DEFAULT_BOOK_SORT, 'identified');
    expect(toggleBookSort(first, 'identified')).toEqual({ key: 'identified', desc: false });
  });

  it('ignores a column the endpoint cannot order by', () => {
    // `_portfolio_sort_key` has no alias for programme, so asking for it would
    // silently return the default order under a header that looks active.
    expect(toggleBookSort(DEFAULT_BOOK_SORT, 'program')).toEqual(DEFAULT_BOOK_SORT);
  });

  it('translates to the alias the endpoint understands', () => {
    expect(bookSortQuery({ key: 'band', desc: false })).toEqual({ sort: 'priority', order: 'asc' });
    expect(bookSortQuery({ key: 'identified', desc: true })).toEqual({ sort: 'identified_usd', order: 'desc' });
    expect(bookSortQuery(undefined)).toEqual({ sort: 'priority', order: 'asc' });
  });

  it('knows when the band ranking has been set aside', () => {
    // The page SAYS this rather than letting the reader notice. A value sort
    // buries a client one hire from a threshold — worth $0 today, the same $0
    // as one fifty hires short.
    expect(ranksByValue({ key: 'identified', desc: true })).toBe(true);
    expect(ranksByValue({ key: 'band', desc: false })).toBe(false);
    // A year sort reorders but does not rank on money, so it makes no such
    // claim and needs no warning.
    expect(ranksByValue({ key: 'year', desc: false })).toBe(false);
  });
});
