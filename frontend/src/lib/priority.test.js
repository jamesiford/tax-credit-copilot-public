import { describe, expect, it } from 'vitest';
import { BAND_ORDER, band, marginReading, trendReading } from './priority.js';

describe('priority bands', () => {
  it('orders by what inaction costs, not by dollar value', () => {
    expect(BAND_ORDER).toEqual([
      'exposed', 'on_the_line', 'declining', 'unclaimed_at_scale', 'not_assessed', 'settled',
    ]);
  });

  it('does not dress a forecast as a finding', () => {
    // `exposed` is a finding against a filed return. `declining` is a
    // projection from a series. They rank next to each other and must not
    // LOOK alike, or the screen turns a projection into an accusation.
    expect(band('declining').tone).not.toBe(band('exposed').tone);
    expect(band('declining').tone).toBe('forecast');
  });

  it('says what has happened, never what will', () => {
    const reading = trendReading({
      declining: true, years_falling: 3, peak_tax_year: 2022,
      fallen_by: 39.33, below_base: true,
    });
    expect(reading.text).toBe('Down 39.3 jobs from TY2022, falling 3 years running.');
    expect(reading.detail).toBe('Now below the base year the credit was earned from.');
  });

  it('has nothing to say about a client that is not falling', () => {
    expect(trendReading(null)).toBeNull();
    expect(trendReading({ declining: false })).toBeNull();
  });

  it('never invents a band for an id it does not know', () => {
    expect(band('nonsense').label).toBe('Unknown');
    expect(band(undefined).rank).toBe(99);
  });

  it('reads a negative margin as a gap and a positive one as headroom', () => {
    expect(marginReading(-0.4).text).toBe('0.4 to qualify');
    expect(marginReading(-0.4).direction).toBe('short');
    expect(marginReading(0.6).text).toBe('0.6 over');
    expect(marginReading(0.6).direction).toBe('over');
    expect(marginReading(0).direction).toBe('at');
  });

  it('says "not measured" rather than guessing at a missing margin', () => {
    // `jobs_to_threshold` returns null when there is no headcount reasoning.
    // Rendering that as 0 would read as "exactly at the line".
    expect(marginReading(null).text).toBe('not measured');
    expect(marginReading(undefined).direction).toBe('unknown');
  });

  it('does not describe an identified credit as outstanding', () => {
    // Whether a client already claimed it is a fact about a filing we do not
    // hold. What we can say is what the engine found.
    expect(band('unclaimed_at_scale').line).toBe('Qualifies, and we have put a figure on it.');
    expect(band('settled').line).toBe('Assessed, and no credit identified.');
  });
});
