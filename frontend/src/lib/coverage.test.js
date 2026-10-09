import { describe, expect, it } from 'vitest';
import {
  BASE_YEAR_NOTE, buildGrid, cellReading, isBaseYear, money, outcomeMeta,
  rankClients, summarise, withUnassessedClients,
} from './coverage.js';

const cell = (overrides = {}) => ({
  program_code: 'GA_JTC',
  tax_year: 2023,
  status: 'claimed',
  provenance: 'computed',
  provenance_verified: true,
  identified_usd: '140000',
  claimed_usd: '100000',
  variance_usd: '40000',
  opportunity_usd: '40000',
  outcome: 'under_claimed',
  is_exposure: false,
  ...overrides,
});

describe('a cell reads as a variance, not a status', () => {
  it('shows recoverable dollars for an under-claim', () => {
    const reading = cellReading(cell());
    expect(reading.tone).toBe('opportunity');
    expect(reading.amount).toBe(40000);
    expect(reading.label).toBe('Under-claimed');
  });

  it('shows a NEGATIVE figure for an over-claim', () => {
    // The distinction the whole product rests on. A grid that rendered "$40k"
    // identically for money owed and money at risk would mislead.
    const reading = cellReading(cell({
      identified_usd: '100000',
      claimed_usd: '140000',
      variance_usd: '-40000',
      opportunity_usd: '0',
      outcome: 'over_claimed',
      is_exposure: true,
    }));
    expect(reading.tone).toBe('exposure');
    expect(reading.amount).toBe(-40000);
    expect(reading.amount).toBeLessThan(0);
  });

  it('carries whether the figure is verified', () => {
    expect(cellReading(cell()).verified).toBe(true);
    expect(cellReading(cell({ provenance_verified: false })).verified).toBe(false);
  });

  it('treats a missing cell as not assessed rather than as zero', () => {
    // "We have not looked" and "there is nothing there" are different claims.
    expect(cellReading(null).outcome).toBe('not_assessed');
    expect(cellReading(undefined).tone).toBe('unknown');
  });
});

describe('a baseline year carries no comparison', () => {
  // Net-new is a year-over-year delta, so the earliest year held shows zero by
  // construction. Comparing a filed amount against it produced a $410,000
  // "over-claim" that was really a statement about our data coverage.
  const baseCell = {
    outcome: 'base_year',
    is_base_year: true,
    variance_usd: null,
    identified_usd: '0',
    claimed_usd: '410000',
    opportunity_usd: '0',
  };

  it('shows no headline figure', () => {
    expect(cellReading(baseCell).amount).toBe(0);
  });

  it('is flagged so a view can explain itself', () => {
    expect(cellReading(baseCell).baseYear).toBe(true);
    expect(isBaseYear(baseCell)).toBe(true);
  });

  it('reads as a baseline, not as a finding', () => {
    expect(cellReading(baseCell).label).toBe('Baseline year');
    expect(cellReading(baseCell).actionable).toBe(false);
  });

  it('ranks below every comparison, so it never leads the grid', () => {
    expect(outcomeMeta('base_year').rank).toBeGreaterThan(outcomeMeta('over_claimed').rank);
    expect(outcomeMeta('base_year').rank).toBeGreaterThan(outcomeMeta('unclaimed').rank);
  });

  it('explains itself without naming a client', () => {
    expect(BASE_YEAR_NOTE).toMatch(/earliest year held/i);
    expect(BASE_YEAR_NOTE).not.toMatch(/candle|bottle|cascade|northwind|ironbridge|halloway/i);
  });

  it('does not treat an ordinary cell as a baseline', () => {
    expect(isBaseYear({ outcome: 'over_claimed', variance_usd: '-63815' })).toBe(false);
    expect(isBaseYear(null)).toBe(false);
  });

  it('leaves a real over-claim reading as an exposure', () => {
    const real = cellReading({
      outcome: 'over_claimed', variance_usd: '-63815', identified_usd: '31185',
      claimed_usd: '95000', opportunity_usd: '0',
    });
    expect(real.tone).toBe('exposure');
    expect(real.amount).toBe(-63815);
    expect(real.baseYear).toBe(false);
  });
});

describe('outcome ordering puts findings first', () => {
  it('ranks exposure above opportunity', () => {
    expect(outcomeMeta('over_claimed').rank).toBeLessThan(outcomeMeta('under_claimed').rank);
  });

  it('ranks anything actionable above settled', () => {
    expect(outcomeMeta('unclaimed').rank).toBeLessThan(outcomeMeta('confirmed').rank);
    expect(outcomeMeta('confirmed').actionable).toBe(false);
  });

  it('does not throw on an unknown outcome', () => {
    expect(outcomeMeta('something_new').label).toBe('something_new');
  });
});

describe('money formatting', () => {
  it('is compact enough for a grid cell', () => {
    expect(money(140000)).toBe('$140k');
    expect(money(1_400_000)).toBe('$1.4M');
    expect(money(850)).toBe('$850');
  });

  it('keeps the sign on a negative', () => {
    expect(money(-40000)).toBe('-$40k');
  });

  it('renders zero as a dash rather than $0', () => {
    expect(money(0)).toBe('—');
    expect(money(null)).toBe('—');
    expect(money('not a number')).toBe('—');
  });
});

describe('buildGrid', () => {
  const cells = [
    cell({ program_code: 'GA_JTC', tax_year: 2022 }),
    cell({ program_code: 'GA_JTC', tax_year: 2023 }),
    cell({ program_code: 'FED_WOTC', tax_year: 2023 }),
  ];

  it('indexes by program and year', () => {
    const grid = buildGrid(cells);
    expect(grid.programs).toEqual(['FED_WOTC', 'GA_JTC']);
    expect(grid.years).toEqual([2022, 2023]);
    expect(grid.at('GA_JTC', 2022)).toBeTruthy();
    expect(grid.at('FED_WOTC', 2022)).toBeNull();
  });

  it('keeps a scope year with no cells as an empty column', () => {
    // A year we can price but have not assessed must render empty, not vanish —
    // a missing column reads as a year that does not exist.
    const grid = buildGrid(cells, { years: [2021, 2022, 2023] });
    expect(grid.years).toEqual([2021, 2022, 2023]);
    expect(grid.at('GA_JTC', 2021)).toBeNull();
  });

  it('does not throw when handed the wrong payload shape', () => {
    // A portfolio response has `clients`, an account response has `cells`. Mid
    // scope-change a component can briefly hold one while rendering the other,
    // and a library function should not be what takes the page down.
    expect(() => buildGrid(undefined)).not.toThrow();
    expect(() => buildGrid(null, { years: [2023] })).not.toThrow();
    expect(buildGrid(undefined).programs).toEqual([]);
    expect(buildGrid(null, { years: [2023] }).years).toEqual([2023]);
  });

  it('handles an empty grid', () => {
    const grid = buildGrid([]);
    expect(grid.programs).toEqual([]);
    expect(grid.at('GA_JTC', 2023)).toBeNull();
  });
});

describe('client ranking surfaces findings', () => {
  it('puts any exposure above every opportunity', () => {
    // Even a small exposure outranks a large opportunity: an exposure is a
    // thing we have discovered and cannot un-know, and burying it under a
    // bigger number is exactly the choice this product must not make.
    const ranked = rankClients([
      { client_id: 1, totals: { opportunity_usd: '900000', exposure_usd: '0' } },
      { client_id: 2, totals: { opportunity_usd: '1000', exposure_usd: '500' } },
    ]);
    expect(ranked[0].client_id).toBe(2);
  });

  it('orders by opportunity when nobody has exposure', () => {
    const ranked = rankClients([
      { client_id: 1, totals: { opportunity_usd: '1000', exposure_usd: '0' } },
      { client_id: 2, totals: { opportunity_usd: '90000', exposure_usd: '0' } },
    ]);
    expect(ranked.map((c) => c.client_id)).toEqual([2, 1]);
  });

  it('does not mutate its input', () => {
    const clients = [
      { client_id: 1, totals: { opportunity_usd: '1000', exposure_usd: '0' } },
      { client_id: 2, totals: { opportunity_usd: '9000', exposure_usd: '0' } },
    ];
    rankClients(clients);
    expect(clients[0].client_id).toBe(1);
  });
});

describe('the book is every client, not every client with a claim', () => {
  const book = [
    { account_id: 1001, name: 'Candle Bottle' },
    { account_id: 2001, name: 'Cascade' },
    { account_id: 2002, name: 'Northwind' },
  ];

  it('keeps a client nobody has assessed visible', () => {
    // Northwind has no claim record. Coverage groups by client FROM CLAIMS, so
    // it was absent from the matrix entirely — and an absent client reads as a
    // client that does not exist rather than one nobody has looked at.
    const rows = withUnassessedClients(
      [{ client_id: 2001, cells: [], totals: { opportunity_usd: '10', exposure_usd: '0' } }],
      book,
    );
    expect(rows.map((r) => r.client_id)).toEqual([2001, 1001, 2002]);
    expect(rows.find((r) => r.client_id === 2002).unassessed).toBe(true);
  });

  it('does not rank the unassessed against the assessed', () => {
    // A client with a real $0 opportunity has been looked at; an unassessed one
    // has not. Sorting them together would put "we found nothing" and "we have
    // not looked" in the same bucket.
    const rows = withUnassessedClients(
      [{ client_id: 2001, cells: [], totals: { opportunity_usd: '0', exposure_usd: '0' } }],
      book,
    );
    expect(rows[0].client_id).toBe(2001);
    expect(rows.slice(1).every((r) => r.unassessed)).toBe(true);
  });

  it('carries no totals for an unassessed client', () => {
    const [row] = withUnassessedClients([], [{ account_id: 2002, name: 'Northwind' }]);
    expect(row.totals).toBeNull();
    expect(row.cells).toEqual([]);
  });

  it('survives an empty book and an empty coverage payload', () => {
    expect(withUnassessedClients(null, null)).toEqual([]);
  });
});

describe('summarise', () => {
  it('keeps the two figures apart', () => {
    const s = summarise({
      opportunity_usd: '340000', exposure_usd: '40000',
      cells: 12, exposure_cells: 1, unverified_cells: 2,
    });
    expect(s.opportunity).toBe(340000);
    expect(s.exposure).toBe(40000);
    expect(s.hasExposure).toBe(true);
    expect(s.unverified).toBe(2);
  });

  it('says there is no exposure rather than showing zero dollars', () => {
    expect(summarise({ opportunity_usd: '100', exposure_usd: '0' }).hasExposure).toBe(false);
  });

  it('survives a missing totals block', () => {
    const s = summarise(undefined);
    expect(s.opportunity).toBe(0);
    expect(s.hasExposure).toBe(false);
  });
});
