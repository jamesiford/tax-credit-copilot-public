import { describe, expect, it } from 'vitest';
import {
  MONTH_LABELS, baseYearChoices, buildBlocks, contributorsFrom, creditColumns, designationCode, designationTitle,
  formatRebase, parseRebase, rebaseBlock,
  fmtHeadcount, monthTone,
  pillClass, readingMeta, rowTone, statusMeta, statusSentence, summariseTrend, trendState, unreachableFor,
} from './trendGrid.js';

const row = (over = {}) => ({
  tax_year: 2023,
  month_totals: Array(12).fill(10),
  total: 120,
  average_headcount: 10,
  months_with_headcount: 12,
  feins: ['58-1'],
  tier: 1,
  tier_source: 'prototype',
  net_new_vs_base: 4,
  threshold: 2,
  qualified: true,
  backfilled: false,
  is_base_year: false,
  status: 'above_minimum',
  ...over,
});

const unit = (over = {}) => ({
  unit_id: 'GA_A',
  name: 'Location A',
  feins: ['58-1'],
  county: 'Chatham',
  census_tract: '',
  base_year: 2022,
  rows: [row({ tax_year: 2022, is_base_year: true, status: 'base', qualified: false, net_new_vs_base: 0 }), row()],
  credit_years: [
    { tax_year: 2022, claimable_usd: 0, projected: false },
    { tax_year: 2023, claimable_usd: 14000, projected: false },
  ],
  total_annual_credit_usd: 14000,
  ...over,
});

describe('which state the grid asks about', () => {
  const OPTIONS = {
    programs: [
      { program_code: 'CO_EZ', calculable: false, jurisdiction: { level: 'state', code: 'CO' } },
      { program_code: 'GA_JTC', calculable: true, jurisdiction: { level: 'state', code: 'GA' } },
      { program_code: 'NY_EXCELSIOR', calculable: true, jurisdiction: { level: 'state', code: 'NY' } },
    ],
  };

  it('uses the selected programme when there is one', () => {
    expect(trendState({ programCode: 'NY_EXCELSIOR' }, OPTIONS, {})).toBe('NY');
  });

  it('skips a programme with no authored years', () => {
    // Alphabetical order put Colorado first, and asking for a state the statute
    // cannot price 404s the whole landing screen.
    expect(trendState({ programCode: 'all' }, OPTIONS, { states: ['GA'] })).toBe('GA');
  });

  it('prefers a state the client actually has payroll in', () => {
    expect(trendState({ programCode: 'all' }, OPTIONS, { states: ['NY'] })).toBe('NY');
  });

  it('answers with nothing rather than a guess when no programme is priceable', () => {
    expect(trendState({ programCode: 'all' }, { programs: [] }, {})).toBe('');
  });
});

describe('the colour rule', () => {
  it('gives every reading exactly one tone', () => {
    const tones = ['base', 'above_minimum', 'below_minimum', 'partial', 'no_data']
      .map((status) => statusMeta(status).tone);
    expect(tones).toEqual(['accent', 'green', 'bad', 'amber', 'muted']);
  });

  it('never invents a tone for a status the backend has not defined', () => {
    expect(statusMeta('something_new').tone).toBe('muted');
    expect(rowTone({ status: undefined })).toBe('muted');
  });

  it('maps each tone onto a badge class the stylesheet actually ships', () => {
    const classes = ['accent', 'green', 'amber', 'bad', 'muted'].map(pillClass);
    expect(classes).toEqual(['pill-accent', 'pill-ok', 'pill-warn', 'pill-bad', 'pill-neutral']);
  });

  it('leaves a month with no headcount neutral rather than calling it a loss', () => {
    expect(monthTone(0, { baseMonthlyAverage: 10 })).toBe('muted');
    expect(monthTone(null, { baseMonthlyAverage: 10 })).toBe('muted');
  });

  it('never colours a month nothing reaches when nothing was counted in it', () => {
    // The zero is a fact about the pay calendar. Red would invent a finding.
    expect(monthTone(0, { baseMonthlyAverage: 10, unreachable: true })).toBe('muted');
  });

  it('reads a Month-12-rule count like any other month (29 Sep)', () => {
    // Nothing spans 31 Dec, but each employee's last period end after the 15th
    // is the agreed target. That count is valid, so it is read against the minimum.
    expect(monthTone(4, { baseMonthlyAverage: 10, threshold: 2, unreachable: true })).toBe('bad');
    expect(monthTone(12, { baseMonthlyAverage: 10, threshold: 2, unreachable: true })).toBe('green');
  });

  it('reads a month against the minimum, not against the row verdict', () => {
    expect(monthTone(12, { baseMonthlyAverage: 10, threshold: 2 })).toBe('green');
    expect(monthTone(8, { baseMonthlyAverage: 10, threshold: 2 })).toBe('bad');
    expect(monthTone(10, { baseMonthlyAverage: 10, isBaseYear: true })).toBe('accent');
  });

  it('paints a month above the base but under the minimum red (30 Sep)', () => {
    // GA-007: base 20.17, two-job minimum, so 22.17 qualifies. A 21 is above
    // the base and still short — green told the reader it qualified.
    expect(monthTone(21, { baseMonthlyAverage: 20.17, threshold: 2 })).toBe('bad');
    expect(monthTone(22, { baseMonthlyAverage: 20.17, threshold: 2 })).toBe('bad');
    expect(monthTone(23, { baseMonthlyAverage: 20.17, threshold: 2 })).toBe('green');
    // Qualifying is net new >= the threshold, so exactly at the minimum is green.
    expect(monthTone(12, { baseMonthlyAverage: 10, threshold: 2 })).toBe('green');
    expect(monthTone(10, { baseMonthlyAverage: 10, threshold: 2 })).toBe('bad');
  });
});

describe('the derived note', () => {
  it('says what the rows prove and nothing more', () => {
    expect(statusSentence(unit())).toContain('Above the 2-job minimum in 2023');
    expect(statusSentence(unit())).toContain('1 of 1 years qualify');
  });

  it('calls out a year that dipped below the minimum', () => {
    const dipped = unit({
      rows: [
        row({ tax_year: 2022, is_base_year: true, status: 'base' }),
        row({ tax_year: 2023, qualified: false, status: 'below_minimum', net_new_vs_base: 1 }),
      ],
    });
    expect(statusSentence(dipped)).toContain('Dipped below the 2-job minimum in 2023');
  });

  it('names a backfill year, because re-qualifying is the finding', () => {
    const backfilled = unit({
      rows: [
        row({ tax_year: 2022, is_base_year: true, status: 'base' }),
        row({ tax_year: 2023, backfilled: true }),
      ],
    });
    expect(statusSentence(backfilled)).toContain('Backfilled in 2023');
  });

  it('does not compare a base year against itself', () => {
    const baseOnly = unit({ rows: [row({ tax_year: 2022, is_base_year: true, status: 'base' })] });
    expect(statusSentence(baseOnly)).toContain('Base year only');
  });
});

describe('block ordering', () => {
  it('puts the locations that need attention first', () => {
    const healthy = unit({ unit_id: 'GA_OK', total_annual_credit_usd: 50000 });
    const dipped = unit({
      unit_id: 'GA_BAD',
      total_annual_credit_usd: 1000,
      rows: [
        row({ tax_year: 2022, is_base_year: true, status: 'base' }),
        row({ tax_year: 2023, qualified: false, status: 'below_minimum' }),
      ],
    });

    const blocks = buildBlocks({ units: [healthy, dipped] });
    expect(blocks.map((b) => b.unit_id)).toEqual(['GA_BAD', 'GA_OK']);
    expect(blocks[0].attention).toBe(true);
  });

  it('carries the base year monthly average so month cells have a reference', () => {
    const [block] = buildBlocks({ units: [unit()] });
    expect(block.baseMonthlyAverage).toBe(10);
  });

  it('survives a payload with no units', () => {
    expect(buildBlocks(null)).toEqual([]);
    expect(buildBlocks({ units: [] })).toEqual([]);
  });
});

describe('credit columns', () => {
  it('labels the stream YR1..YRn off the base year', () => {
    expect(creditColumns(unit()).map((c) => c.label)).toEqual(['YR1', 'YR2']);
  });
});

describe('the roll-up strip', () => {
  it('counts locations rather than re-deriving dollars', () => {
    const payload = {
      units: [unit()],
      years: [2022, 2023],
      totals: { annual_credit_usd: 14000, tranche_lifetime_usd: 70000 },
      declined_years: [{ tax_year: '2019', reason: 'no rule pack' }],
    };
    const totals = summariseTrend(payload, buildBlocks(payload));

    expect(totals.locations).toBe(1);
    expect(totals.yearRange).toBe('TY2022–TY2023');
    expect(totals.qualifyingLocations).toBe(1);
    expect(totals.annualCreditUsd).toBe(14000);
    expect(totals.declinedYears).toHaveLength(1);
  });
});

describe('unreachable months', () => {
  const payload = {
    year_meta: [
      { tax_year: 2023, unreachable_months: [0, 11] },
      { tax_year: 2024, unreachable_months: [] },
    ],
  };

  it('reads the positions the backend named', () => {
    expect([...unreachableFor(payload, 2023)]).toEqual([0, 11]);
    expect([...unreachableFor(payload, 2024)]).toEqual([]);
  });

  it('assumes nothing for a year it was told nothing about', () => {
    expect([...unreachableFor(payload, 2099)]).toEqual([]);
    expect([...unreachableFor(null, 2023)]).toEqual([]);
  });
});

describe('who is behind a cell', () => {
  const months = (...indexes) => {
    const out = Array(12).fill(0);
    indexes.forEach((i) => { out[i] = 1; });
    return out;
  };
  const MATRIX = {
    matrix: [
      { record_token: 't1', employee_id: 'B', unit_id: 'GA_A', months: months(0, 1) },
      { record_token: 't2', employee_id: 'A', unit_id: 'GA_A', months: months(0) },
      { record_token: 't3', employee_id: 'C', unit_id: 'GA_B', months: months(0) },
    ],
  };

  it('names only the people counted at that location in that month', () => {
    expect(contributorsFrom(MATRIX, 'GA_A', 0).map((p) => p.employee_id)).toEqual(['A', 'B']);
    expect(contributorsFrom(MATRIX, 'GA_A', 1).map((p) => p.employee_id)).toEqual(['B']);
  });

  it('returns nobody for a month nothing reached', () => {
    expect(contributorsFrom(MATRIX, 'GA_A', 5)).toEqual([]);
  });

  it('counts the whole year when no month is given', () => {
    const year = contributorsFrom(MATRIX, 'GA_A', null);
    expect(year.map((p) => [p.employee_id, p.counted])).toEqual([['A', 1], ['B', 2]]);
  });

  it('answers "how many people", not "how many segments"', () => {
    const split = {
      matrix: [
        { record_token: 't1', employee_id: 'A', unit_id: 'GA_A', months: months(0) },
        { record_token: 't1', employee_id: 'A', unit_id: 'GA_A', months: months(0) },
      ],
    };
    expect(contributorsFrom(split, 'GA_A', 0)).toHaveLength(1);
  });

  it('survives an empty or absent matrix', () => {
    expect(contributorsFrom(null, 'GA_A', 0)).toEqual([]);
    expect(contributorsFrom({ matrix: [] }, 'GA_A', 0)).toEqual([]);
  });
});

describe('formatting', () => {
  it('shows a whole person as a whole number and a fraction as one decimal', () => {
    expect(fmtHeadcount(7)).toBe('7');
    expect(fmtHeadcount(7.5)).toBe('7.5');
  });

  it('renders an absent count as a dash rather than a zero', () => {
    expect(fmtHeadcount(0)).toBe('—');
    expect(fmtHeadcount(undefined)).toBe('—');
  });

  it('has twelve month columns', () => {
    expect(MONTH_LABELS).toHaveLength(12);
  });
});


describe('the designation a location-year shows', () => {
  it('reads the partner\u2019s codes as they are', () => {
    expect(designationCode({ tier: 1, designation: 'T1 B40', tier_source: 'prototype' })).toBe('T1 B40');
    expect(designationCode({ tier: 1, designation: 'T1', tier_source: 'prototype' })).toBe('T1');
  });

  it('says Unassigned rather than guessing a tier', () => {
    expect(designationCode({ tier: null, designation: null, tier_source: 'unassigned' })).toBe('Unassigned');
    expect(designationCode(undefined)).toBe('Unassigned');
  });

  it('reads a legacy sentence as its tier', () => {
    expect(designationCode({ tier: 2, designation: 'Tier 2 — Less Developed Census Tract', tier_source: 'prototype' })).toBe('T2');
  });

  it('says on hover that it is shown, not applied', () => {
    const title = designationTitle({ tax_year: 2021, tier: 1, designation: 'T1 B40', tier_source: 'prototype' });
    expect(title).toMatch(/40 least developed counties/);
    expect(title).toMatch(/TY2021/);
    expect(title).toMatch(/not applied by the engine/);
  });
});


describe('the base-year picker (WI-21)', () => {
  const block = {
    unit_id: 'GA_GA-010',
    total_annual_credit_usd: 140000,
    rows: [2020, 2021, 2022, 2023].map((y) => ({
      tax_year: y, average_headcount: 10 + (y - 2020) * 3, is_base_year: y === 2020,
      status: y === 2020 ? 'base' : 'above_minimum', qualified: y !== 2020,
      months_with_headcount: y === 2021 ? 6 : 11, months_reachable: 11,
    })),
  };
  const rebase = {
    worksite_id: 'GA_GA-010', base_year: 2022, inferred_base_year: 2020,
    total_annual_credit_usd: 10500, run_total_annual_credit_usd: 140000, delta_annual_credit_usd: -129500,
    years: [
      { tax_year: 2020, role: 'before_base', status: 'before_base' },
      { tax_year: 2021, role: 'before_base', status: 'before_base' },
      { tax_year: 2022, role: 'base', status: 'base' },
      { tax_year: 2023, role: 'evaluated', year_number: 1, status: 'above_minimum', qualified: true, net_new_vs_base: 3, annual_credit_usd: 10500 },
    ],
  };

  it('round-trips the chosen bases through the URL, and drops what does not parse', () => {
    const map = parseRebase('GA_GA-013:2021,GA_GA-010:2022,nonsense,GA_X:abc');
    expect(map).toEqual({ 'GA_GA-013': 2021, 'GA_GA-010': 2022 });
    expect(formatRebase(map)).toBe('GA_GA-010:2022,GA_GA-013:2021');
  });

  it('offers only complete years as a base', () => {
    expect(baseYearChoices(block)).toEqual([2020, 2022, 2023]);
  });

  it('re-shapes the block from the rebase read: before, base, year one', () => {
    const next = rebaseBlock(block, rebase);
    expect(next.rows.map((r) => r.status)).toEqual(['before_base', 'before_base', 'base', 'above_minimum']);
    expect(next.rows[3].year_number).toBe(1);
    expect(next.baseMonthlyAverage).toBe(16);
    expect(next.total_annual_credit_usd).toBe(10500);
    expect(next.rebased).toMatchObject({ base_year: 2022, inferred_base_year: 2020, delta_annual_credit_usd: -129500 });
  });

  it('leaves a block alone when the rebase is for another location', () => {
    expect(rebaseBlock(block, { ...rebase, worksite_id: 'GA_GA-001' })).toBe(block);
  });
});

describe('an open year (TY2026)', () => {
  const open = (over = {}) => row({ tax_year: 2024, status: 'in_progress', months_reachable: 8, months_with_headcount: 8, ...over });

  it('reads On track or Behind pace, as an outline, never as a verdict', () => {
    expect(readingMeta(open()).label).toBe('On track');
    expect(readingMeta(open({ qualified: false })).label).toBe('Behind pace');
    expect(pillClass(readingMeta(open()).tone)).toBe('pill-forecast-ok');
    expect(pillClass(readingMeta(open({ qualified: false })).tone)).toBe('pill-forecast-bad');
    expect(readingMeta(row()).label).toBe(statusMeta('above_minimum').label);
    expect(rowTone(open({ qualified: false }))).toBe('forecast-bad');
  });

  it('is never offered as a base year, although its closed months look complete', () => {
    const block = unit({ rows: [row({ tax_year: 2022, is_base_year: true, status: 'base' }), row(), open()] });
    expect(baseYearChoices(block)).toEqual([2022, 2023]);
  });

  it('keeps "qualify" about finished years and counts on-track apart', () => {
    const blocks = buildBlocks({
      units: [
        unit({ rows: [row({ tax_year: 2022, is_base_year: true, status: 'base' }), row(), open({ qualified: false })] }),
        unit({ unit_id: 'GA_B', rows: [row({ tax_year: 2022, is_base_year: true, status: 'base' }), row({ qualified: false, status: 'below_minimum' }), open()] }),
      ],
      years: [2022, 2023, 2024],
    });
    const totals = summariseTrend({ years: [2022, 2023, 2024] }, blocks);
    expect(totals.qualifyingLocations).toBe(1);
    expect(totals.attentionLocations).toBe(1);
    expect(totals).toMatchObject({ openYear: 2024, openLocations: 2, onTrackLocations: 1 });
  });

  it('says where the open year stands, on its closed months', () => {
    const sentence = statusSentence(unit({ rows: [row({ tax_year: 2022, is_base_year: true, status: 'base' }), row(), open({ qualified: false, net_new_vs_base: 0.5 })] }));
    expect(sentence).toContain('Behind pace in 2024: 0.5 net-new over 8 closed months');
    expect(sentence).toContain('1 of 1 years qualify');
  });
});
