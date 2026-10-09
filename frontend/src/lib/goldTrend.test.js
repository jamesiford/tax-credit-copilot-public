import { describe, expect, it } from 'vitest';
import { monthTotals, trendFromGold, unreachableMonths } from './goldTrend.js';

const item = (over = {}) => ({
  client_id: 1001,
  worksite_id: 'GA_A',
  entity_fein: '12-3456789',
  program_code: 'GA_JTC',
  method: 'min_max',
  tax_year: 2023,
  average_headcount: 16,
  is_base_year: false,
  base_average_headcount: 14,
  base_year_source: 'inferred',
  net_new_vs_base: 2,
  months_reachable: 12,
  qualified: true,
  status: 'above_minimum',
  threshold: 2,
  threshold_source: 'rule_pack',
  eligible_jobs: 2,
  new_jobs_created: 2,
  high_water_mark: 16,
  per_job_usd: '3500.0000',
  tranche_years: 5,
  annual_credit_usd: '7000.0000',
  run_id: 'R1',
  is_current: true,
  ...over,
});

const summary = (over = {}) => ({
  worksite_id: 'GA_A',
  tax_year: 2023,
  ...Object.fromEntries(
    Array.from({ length: 12 }, (_, i) => [`month_${String(i + 1).padStart(2, '0')}`, 16]),
  ),
  total: 192,
  average_headcount: 16,
  months_with_headcount: 12,
  unreachable_months: null,
  ...over,
});

const payload = (over = {}) => ({
  calculation_state: 'calculated',
  run: { run_id: 'R1' },
  items: [item({ tax_year: 2022, is_base_year: true, status: 'base', qualified: false, net_new_vs_base: 0 }), item()],
  months: [summary({ tax_year: 2022 }), summary()],
  installments: [
    { worksite_id: 'GA_A', tax_year: 2023, claimable_usd: '7000.0000', projected: false, creation_year: 2023 },
    { worksite_id: 'GA_A', tax_year: 2024, claimable_usd: '7000.0000', projected: true, creation_year: 2023 },
  ],
  unit_totals: [{
    worksite_id: 'GA_A',
    total_annual_credit_usd: '7000.0000',
    total_tranche_lifetime_usd: '14000.0000',
    final_high_water_mark: 16,
  }],
  units: [{ worksite_id: 'GA_A', name: 'Atlanta', county: 'Fulton', city: 'Atlanta' }],
  ...over,
});

describe('monthTotals', () => {
  it('reads the twelve columns in order', () => {
    expect(monthTotals(summary({ month_01: 1, month_12: 12 }))).toEqual(
      [1, 16, 16, 16, 16, 16, 16, 16, 16, 16, 16, 12],
    );
  });

  it('is twelve zeroes when the unit has no monthly row', () => {
    expect(monthTotals(null)).toEqual(Array(12).fill(0));
  });
});

describe('unreachableMonths', () => {
  it('parses the stored csv', () => {
    expect(unreachableMonths(summary({ unreachable_months: '10,11' }))).toEqual([10, 11]);
  });

  it('is empty when every month is reachable', () => {
    expect(unreachableMonths(summary())).toEqual([]);
    expect(unreachableMonths(undefined)).toEqual([]);
  });
});

describe('trendFromGold', () => {
  it('groups flat unit-year rows into one block per location', () => {
    const { units, years } = trendFromGold(payload());

    expect(units).toHaveLength(1);
    expect(years).toEqual([2022, 2023]);
    expect(units[0].unit_id).toBe('GA_A');
    expect(units[0].rows.map((r) => r.tax_year)).toEqual([2022, 2023]);
  });

  it('keeps the warehouse vocabulary rather than renaming it', () => {
    const [unit] = trendFromGold(payload()).units;
    const latest = unit.rows[1];

    // Gold spells it net_new_vs_base. Renaming to `net_new` would put two names
    // on one quantity, which is how the SQL and the screen drift apart.
    expect(latest.net_new_vs_base).toBe(2);
    expect(latest.net_new).toBeUndefined();
  });

  it('attaches the monthly cells to the year they belong to', () => {
    const [unit] = trendFromGold(payload()).units;
    expect(unit.rows[1].month_totals).toHaveLength(12);
    expect(unit.rows[1].total).toBe(192);
    expect(unit.rows[1].months_with_headcount).toBe(12);
  });

  it('carries the credit columns, which no other table can supply', () => {
    const [unit] = trendFromGold(payload()).units;
    expect(unit.credit_years.map((c) => c.tax_year)).toEqual([2023, 2024]);
    expect(unit.credit_years[1].projected).toBe(true);
  });

  it('takes per-unit money as SQL summed it, not by adding on screen', () => {
    const [unit] = trendFromGold(payload()).units;
    expect(unit.total_annual_credit_usd).toBe(7000);
    expect(unit.total_tranche_lifetime_usd).toBe(14000);
  });

  it('finds the base year from the row that declares it', () => {
    const [unit] = trendFromGold(payload()).units;
    expect(unit.base_year).toBe(2022);
    expect(unit.base_average_headcount).toBe(14);
  });

  it('joins the dimension attributes the warehouse does not duplicate', () => {
    const [unit] = trendFromGold(payload()).units;
    expect(unit.name).toBe('Atlanta');
    expect(unit.county).toBe('Fulton');
  });

  it('falls back to the id rather than inventing a name', () => {
    const [unit] = trendFromGold(payload({ units: [] })).units;
    expect(unit.name).toBe('GA_A');
    expect(unit.county).toBe('');
  });

  it('surfaces unreachable months per year', () => {
    const body = payload({ months: [summary({ unreachable_months: '11' }), summary({ tax_year: 2022 })] });
    const meta = trendFromGold(body).year_meta.find((m) => m.tax_year === 2023);
    expect(meta.unreachable_months).toEqual([11]);
  });

  it('is empty for a client with no run, and says nothing more', () => {
    expect(trendFromGold({ calculation_state: 'not_calculated', items: [] })).toEqual({
      units: [], years: [], year_meta: [], totals: {},
    });
    expect(trendFromGold(null).units).toEqual([]);
  });
});
