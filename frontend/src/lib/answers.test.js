import { describe, expect, it } from 'vitest';
import {
  clientAnswer, decisionBreakdown, employeeAnswer, portfolioAnswer, unitAnswer, withinBand,
} from './answers.js';

describe('the unit answer names the cohort nobody could see before', () => {
  const payload = {
    employees: Array.from({ length: 29 }, (_, i) => ({ record_token: `q${i}` })),
    thresholds: { min_weekly_hours: 35, min_weekly_wages: 636, resolved: true },
    near_threshold: [
      { record_token: 'n1', avg_weekly_hours: 34.81 },
      { record_token: 'n2', avg_weekly_hours: 33.2 },
      { record_token: 'n3', avg_weekly_hours: 31.0 },
      { record_token: 'n4', avg_weekly_hours: 30.0 },
      { record_token: 'n5', avg_weekly_hours: 28.64 },
      { record_token: 'n6', avg_weekly_hours: 12.0 },
      { record_token: 'n7', avg_weekly_hours: 4.0 },
    ],
  };

  it('counts only the near misses inside the band', () => {
    // GA_GA-001: seven ineligible in all, four of them within five hours.
    expect(unitAnswer(payload, 4)).toBe(
      '29 employees · 29 counted in May · 4 more within 5 hrs of the 35-hr floor.',
    );
    expect(withinBand(payload)).toHaveLength(4);
  });

  it('takes the floor from the rule pack, never from a constant', () => {
    // A different jurisdiction, a different floor — and a different count: at a
    // 30-hour floor the band reaches down to 25 and catches one more person.
    const other = { ...payload, thresholds: { min_weekly_hours: 30, resolved: true } };
    expect(unitAnswer(other, null)).toContain('30-hr floor');
    expect(unitAnswer(other, null)).toContain('5 more within 5 hrs');
  });

  it('says nothing about a floor it was not given', () => {
    const unresolved = { ...payload, thresholds: { min_weekly_hours: null, resolved: false } };
    expect(unitAnswer(unresolved, null)).toBe('29 employees.');
  });

  it('omits the clause when nobody is close', () => {
    const none = { ...payload, near_threshold: [{ record_token: 'x', avg_weekly_hours: 4 }] };
    expect(unitAnswer(none, null)).toBe('29 employees.');
  });
});

describe('the client answer', () => {
  it('counts locations once even though a location has a row per year', () => {
    const payload = {
      items: [
        { worksite_id: 'A', tax_year: 2020, qualified: false, is_base_year: true },
        { worksite_id: 'A', tax_year: 2021, qualified: true, is_base_year: false },
        { worksite_id: 'B', tax_year: 2021, qualified: true, is_base_year: false },
      ],
      unit_totals: [
        { total_annual_credit_usd: '600000.0000' },
        { total_annual_credit_usd: '7110.0000' },
      ],
    };
    expect(clientAnswer(payload)).toBe(
      '2 locations · 2 qualify in TY2021 · $607,110 claimable across TY2020–TY2021 · TY2020 base.',
    );
  });

  it('counts the latest year, so it agrees with the strip beneath it (WI-15)', () => {
    // Cascade read "6 qualify" directly above "4 qualify · 2 below the
    // minimum": any-year against latest-year.
    const payload = {
      items: [
        { worksite_id: 'A', tax_year: 2024, qualified: true },
        { worksite_id: 'A', tax_year: 2025, qualified: false },
        { worksite_id: 'B', tax_year: 2024, qualified: true },
        { worksite_id: 'B', tax_year: 2025, qualified: true },
      ],
      unit_totals: [],
    };
    expect(clientAnswer(payload)).toBe('2 locations · 1 qualify in TY2025.');
  });

  it('says "their latest year" when the locations end in different years', () => {
    const payload = {
      items: [
        { worksite_id: 'A', tax_year: 2024, qualified: true },
        { worksite_id: 'B', tax_year: 2025, qualified: true },
      ],
    };
    expect(clientAnswer(payload)).toBe('2 locations · 2 qualify in their latest year.');
  });
});

describe('the portfolio answer', () => {
  it('uses the API totals rather than the rows on screen', () => {
    // The items array is one page; counting it would understate the book.
    const summary = { total_clients: 5, assessed_clients: 4, unassessed_clients: 1, items: [{}] };
    expect(portfolioAnswer(summary, { name: 'Cascade', jobs_margin: -1.2 })).toBe(
      '5 clients · 4 assessed · 1.2 jobs from qualifying: Cascade.',
    );
  });

  it('does not describe a client who is OVER the line as short of it', () => {
    // `gap_jobs` clamps at zero, so somebody 0.58 jobs clear read as "0.0 jobs
    // from qualifying" — naming the client with nothing to do as the closest
    // to needing something. Both sides are `on_the_line`; they are opposite
    // conversations.
    const summary = { total_clients: 5, assessed_clients: 5 };
    expect(portfolioAnswer(summary, { name: 'Northwind', jobs_margin: 0.58 })).toBe(
      '5 clients · 5 assessed · Northwind holds the threshold by 0.6 jobs.',
    );
  });

  it('stays silent about a nearest client it does not have', () => {
    expect(portfolioAnswer({ total_clients: 5, assessed_clients: 4 }, null))
      .toBe('5 clients · 4 assessed.');
  });

  it('returns nothing rather than inventing a denominator', () => {
    expect(portfolioAnswer(null, null)).toBeNull();
  });
});

describe('the employee answer', () => {
  it('states effort against the floor and how much of the year was reached', () => {
    const data = {
      raw_source_rows: Array.from({ length: 162 }, () => ({ selection_decision: 'included' })),
      thresholds: { minimum_average_weekly_hours: 35 },
      step1: { min_max: { avg_weekly_hours: 38.24 } },
      onezero: {
        months: Array.from({ length: 12 }, (_, i) => i + 1),
        min_max: [{ months: [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0] }],
      },
    };
    expect(employeeAnswer(data)).toBe(
      '162 periods · 38.2 avg weekly hrs vs a 35-hr floor · counted in 11 of 12 months.',
    );
  });
});

describe('a reviewer must tell the three exclusions apart', () => {
  it('breaks periods down by WHY, not by whether', () => {
    // `included` is a boolean; it cannot distinguish these.
    const rows = [
      { selection_decision: 'included' },
      { selection_decision: 'included' },
      { selection_decision: 'outside_fiscal_window' },
      { selection_decision: 'shorter_than_seven_days' },
      { selection_decision: 'shorter_than_seven_days' },
      { selection_decision: 'filtered_by_pay_code' },
    ];
    expect(decisionBreakdown(rows)).toEqual([
      { decision: 'included', count: 2 },
      { decision: 'shorter_than_seven_days', count: 2 },
      { decision: 'outside_fiscal_window', count: 1 },
      { decision: 'filtered_by_pay_code', count: 1 },
    ]);
  });

  it('falls back to the boolean only when no reason was recorded', () => {
    expect(decisionBreakdown([{ included: true }, { included: false }])).toEqual([
      { decision: 'included', count: 1 },
      { decision: 'excluded', count: 1 },
    ]);
  });
});

describe('an open year in the page answer (TY2026)', () => {
  it('says qualify about the finished year and on track about the open one', () => {
    const payload = {
      items: [
        { worksite_id: 'A', tax_year: 2025, qualified: true, status: 'above_minimum' },
        { worksite_id: 'A', tax_year: 2026, qualified: false, status: 'in_progress' },
        { worksite_id: 'B', tax_year: 2025, qualified: false, status: 'below_minimum' },
        { worksite_id: 'B', tax_year: 2026, qualified: true, status: 'in_progress' },
      ],
      unit_totals: [],
    };
    expect(clientAnswer(payload)).toBe('2 locations · 1 qualify in TY2025 · 1 of 2 on track in TY2026 so far.');
  });
});
