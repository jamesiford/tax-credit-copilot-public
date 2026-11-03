import { describe, expect, it } from 'vitest';
import {
  activeBookTab, bandCounts, bookTabs, filtersForTab, tileTone,
} from './bookCards.js';

const ROWS = [
  { priority_band: 'settled' },
  { priority_band: 'exposed' },
  { priority_band: 'unclaimed_at_scale' },
  { priority_band: 'unclaimed_at_scale' },
];

describe('the book cards', () => {
  it('counts clients per band in ranking order and omits empty bands', () => {
    expect(bandCounts(ROWS)).toEqual([
      { id: 'exposed', count: 1 },
      { id: 'unclaimed_at_scale', count: 2 },
      { id: 'settled', count: 1 },
    ]);
  });

  it('puts the complete population first and gives every tab a count', () => {
    const tabs = bookTabs(ROWS);
    expect(tabs[0]).toMatchObject({ id: 'all', count: 4 });
    expect(tabs.map((t) => t.count)).toEqual([4, 1, 2, 1]);
  });

  it('maps a band onto the state family it means, never a free colour', () => {
    expect(tileTone('exposed')).toBe('below-min');
    expect(tileTone('unclaimed_at_scale')).toBe('above-min');
    expect(tileTone('on_the_line')).toBe('partial');
    // A projection is not an accusation.
    expect(tileTone('declining')).toBe('partial');
    expect(tileTone('settled')).toBe('neutral');
    expect(tileTone('nonsense')).toBe('neutral');
  });

  it('writes and reads the same band filter the column header writes', () => {
    expect(filtersForTab({ year: '2023' }, 'exposed')).toEqual({ year: '2023', band: 'exposed' });
    expect(filtersForTab({ band: 'exposed', year: '2023' }, 'all')).toEqual({ year: '2023' });
    expect(activeBookTab({})).toBe('all');
    expect(activeBookTab({ band: 'exposed' })).toBe('exposed');
    // A mix chosen in the header selects no single tab.
    expect(activeBookTab({ band: 'exposed|settled' })).toBeNull();
  });
});
