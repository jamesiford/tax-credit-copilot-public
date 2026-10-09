import { describe, expect, it } from 'vitest';
import {
  ALL_PROGRAMS, PORTFOLIO, calculableYears, derivedJurisdictions, initialScope,
  placeholderYears, reconcileScope, scopeLabel, unpriceableYears, windowFor,
} from './scopeDimension.js';

const OPTIONS = {
  clients: [
    { account_id: 1001, name: 'Candle Bottle', synthetic: false },
    { account_id: 2001, name: 'Cascade Retail Partners', synthetic: true },
  ],
  programs: [
    {
      program_code: 'GA_JTC',
      name: 'Georgia Jobs Tax Credit',
      jurisdiction: { level: 'state', code: 'GA', name: 'Georgia' },
      authored_years: [2020, 2021, 2022, 2023, 2024, 2025],
      calculable: true,
      not_calculable_reason: '',
    },
    {
      program_code: 'SC_JTC',
      name: 'South Carolina Jobs Tax Credit',
      jurisdiction: { level: 'state', code: 'SC', name: 'South Carolina' },
      authored_years: [],
      calculable: false,
      not_calculable_reason: 'No year-scoped rule packs authored for sc_jtc.',
    },
  ],
  years: { authored: [2020, 2021, 2022, 2023, 2024, 2025], latest: 2025, window_years: 6 },
};

const CASCADE = {
  account_id: 2001,
  states: ['GA', 'NC', 'SC'],
  payroll_years: [2020, 2021, 2022, 2023, 2024, 2025, 2026],
  calculable_years: [2020, 2021, 2022, 2023, 2024, 2025],
  payroll_without_statute: [2026],
  rows: 76086,
};

// Candle Bottle's 53-week TY2023 window spills into calendar 2024, so its payroll
// years are 2023-2024 even though only one tax year was ever certified.
const CANDLE_BOTTLE = {
  account_id: 1001,
  states: ['GA'],
  payroll_years: [2023, 2024],
  calculable_years: [2023, 2024],
  payroll_without_statute: [],
  rows: 384433,
};

describe('jurisdiction is derived, never selected', () => {
  it('resolves to the selected programme\'s jurisdiction', () => {
    const j = derivedJurisdictions({ ...initialScope, programCode: 'GA_JTC' }, OPTIONS);
    expect(j).toEqual([{ level: 'state', code: 'GA', name: 'Georgia' }]);
  });

  it('lists every jurisdiction in play when all programmes are selected', () => {
    const j = derivedJurisdictions({ ...initialScope, programCode: ALL_PROGRAMS }, OPTIONS);
    expect(j.map((x) => x.code)).toEqual(['GA', 'SC']);
  });

  it('returns nothing for an unknown programme rather than guessing', () => {
    expect(derivedJurisdictions({ ...initialScope, programCode: 'XX_NOPE' }, OPTIONS)).toEqual([]);
  });
});

describe('calculable years intersect statute with payroll', () => {
  it('is statute-only when no client is selected', () => {
    expect(calculableYears(OPTIONS, null, 'GA_JTC')).toEqual([2020, 2021, 2022, 2023, 2024, 2025]);
  });

  it('drops a payroll year with no authored statute', () => {
    const years = calculableYears(OPTIONS, CASCADE, 'GA_JTC');
    expect(years).not.toContain(2026);
    expect(years).toEqual([2020, 2021, 2022, 2023, 2024, 2025]);
  });

  it('drops a statute year the client has no payroll for', () => {
    expect(calculableYears(OPTIONS, CANDLE_BOTTLE, 'GA_JTC')).toEqual([2023, 2024]);
  });

  it('is empty for a programme with no authored years', () => {
    expect(calculableYears(OPTIONS, CASCADE, 'SC_JTC')).toEqual([]);
  });
});

describe('unpriceable years are surfaced, not dropped', () => {
  it('reports payroll we hold but cannot price', () => {
    expect(unpriceableYears(CASCADE)).toEqual([2026]);
  });

  it('is empty when everything can be priced', () => {
    expect(unpriceableYears(CANDLE_BOTTLE)).toEqual([]);
  });
});

describe('reconcileScope', () => {
  it('defaults to the most recent calculable year', () => {
    const { scope } = reconcileScope({ ...initialScope }, OPTIONS, CASCADE);
    expect(scope.year).toBe(2025);
  });

  it('moves an impossible year and SAYS SO', () => {
    // The critical case: switching from Cascade to Candle Bottle while sitting on
    // TY2020. Silently recomputing under TY2024's statute would be a wrong
    // number presented as a right one.
    const { scope, notices } = reconcileScope(
      { ...initialScope, clientId: 1001, year: 2020 }, OPTIONS, CANDLE_BOTTLE,
    );
    expect(scope.year).toBe(2024);
    expect(notices).toHaveLength(1);
    expect(notices[0].axis).toBe('year');
    expect(notices[0].message).toContain('TY2020');
    expect(notices[0].message).toContain('TY2024');
  });

  it('keeps a year that is still valid after switching client', () => {
    const { scope, notices } = reconcileScope(
      { ...initialScope, clientId: 1001, year: 2023 }, OPTIONS, CANDLE_BOTTLE,
    );
    expect(scope.year).toBe(2023);
    expect(notices).toHaveLength(0);
  });

  it('lands a cold client page on the complete year, not the newest partial one', () => {
    // /c/1001 opened cold: the client's payroll has not arrived, so the first
    // pass picks from the statute (TY2025). When it arrives TY2025 is gone, and
    // the fallback used to take the newest payroll year — TY2024, two months no
    // run has priced — so the page asked for a year that could only 404.
    const cold = reconcileScope({ ...initialScope, clientId: 1001, programCode: 'GA_JTC' }, OPTIONS, null);
    expect(cold.scope.year).toBe(2025);
    const { scope, notices } = reconcileScope(
      cold.scope, OPTIONS, { ...CANDLE_BOTTLE, complete_years: [2023], default_year: 2023 },
    );
    expect(scope.year).toBe(2023);
    expect(notices[0].message).toContain('TY2023');
  });

  it('falls back to all programmes when one disappears', () => {
    const { scope, notices } = reconcileScope(
      { ...initialScope, programCode: 'GONE' }, OPTIONS, CASCADE,
    );
    // GA_JTC, not ALL_PROGRAMS: the fallback drops the unknown code, and the
    // resolution below it then names the only programme we can price. What
    // matters is that the operator is TOLD their selection was not honoured.
    expect(scope.programCode).toBe('GA_JTC');
    expect(notices[0].axis).toBe('program');
  });

  describe('a lone calculable programme is resolved, never left as "all"', () => {
    // "all" is honest at the book and a dead end everywhere else: Progress and
    // What-if need one statute and render "Select a single program" without
    // it. With the scope bar gone from the shell there was no way out of that
    // state, so two of the three demo views were unreachable.
    it('resolves when exactly one programme is calculable', () => {
      const { scope } = reconcileScope({ ...initialScope }, OPTIONS, CASCADE);
      expect(scope.programCode).toBe('GA_JTC');
    });

    it('leaves the choice alone when two are calculable, because it is a real one', () => {
      const two = {
        ...OPTIONS,
        programs: [
          OPTIONS.programs[0],
          { ...OPTIONS.programs[1], calculable: true, authored_years: [2024] },
        ],
      };
      const { scope } = reconcileScope({ ...initialScope }, two, CASCADE);
      expect(scope.programCode).toBe(ALL_PROGRAMS);
    });

    it('leaves it alone when none can be calculated', () => {
      const none = {
        ...OPTIONS,
        programs: OPTIONS.programs.map((p) => ({ ...p, calculable: false })),
      };
      const { scope } = reconcileScope({ ...initialScope }, none, CASCADE);
      expect(scope.programCode).toBe(ALL_PROGRAMS);
    });

    it('never overwrites a programme the operator chose', () => {
      const { scope } = reconcileScope(
        { ...initialScope, programCode: 'SC_JTC' }, OPTIONS, CASCADE,
      );
      expect(scope.programCode).toBe('SC_JTC');
    });
  });

  it('explains an uncalculable programme instead of silently emptying', () => {
    const { notices, availableYears } = reconcileScope(
      { ...initialScope, programCode: 'SC_JTC' }, OPTIONS, CASCADE,
    );
    expect(availableYears).toEqual([]);
    expect(notices.map((n) => n.axis)).toContain('program');
    expect(notices.find((n) => n.axis === 'program').message).toContain('sc_jtc');
  });

  it('nulls the year when nothing can be calculated', () => {
    const { scope } = reconcileScope(
      { ...initialScope, programCode: 'SC_JTC', year: 2023 }, OPTIONS, CASCADE,
    );
    expect(scope.year).toBeNull();
  });

  it('returns a single-year window by default', () => {
    const { window } = reconcileScope({ ...initialScope, year: 2023 }, OPTIONS, CASCADE);
    expect(window).toEqual([2023]);
  });

  it('returns the retroactive window when windowMode is on', () => {
    const { window } = reconcileScope(
      { ...initialScope, year: 2025, windowMode: true }, OPTIONS, CASCADE,
    );
    expect(window).toEqual([2020, 2021, 2022, 2023, 2024, 2025]);
  });

  it('clips the window to years that actually exist', () => {
    // Candle Bottle only holds two years; a six-year window must not invent four.
    const { window } = reconcileScope(
      { ...initialScope, clientId: 1001, year: 2024, windowMode: true }, OPTIONS, CANDLE_BOTTLE,
    );
    expect(window).toEqual([2023, 2024]);
  });

  it('does not mutate the scope it was given', () => {
    const original = { ...initialScope, year: 2020, clientId: 1001 };
    const snapshot = { ...original };
    reconcileScope(original, OPTIONS, CANDLE_BOTTLE);
    expect(original).toEqual(snapshot);
  });

  it('survives absent options rather than throwing', () => {
    const { scope, availableYears } = reconcileScope({ ...initialScope }, null, null);
    expect(availableYears).toEqual([]);
    expect(scope.year).toBeNull();
  });
});

describe('windowFor', () => {
  const available = [2019, 2020, 2021, 2022, 2023, 2024, 2025];

  it('is a base year plus five', () => {
    expect(windowFor(2025, available)).toEqual([2020, 2021, 2022, 2023, 2024, 2025]);
  });

  it('never reaches past the selected year', () => {
    expect(windowFor(2022, available)).toEqual([2019, 2020, 2021, 2022]);
  });

  it('is empty without a year', () => {
    expect(windowFor(null, available)).toEqual([]);
  });
});

describe('scopeLabel', () => {
  it('reads as portfolio by default', () => {
    const label = scopeLabel({ ...initialScope, year: 2025 }, OPTIONS, null);
    expect(label).toBe('All clients \u00b7 All programs \u00b7 TY2025');
  });

  it('names the client and programme when narrowed', () => {
    const label = scopeLabel(
      { clientId: 2001, programCode: 'GA_JTC', year: 2023, windowMode: false }, OPTIONS, CASCADE,
    );
    expect(label).toBe('Cascade Retail Partners \u00b7 Georgia Jobs Tax Credit \u00b7 TY2023');
  });

  it('shows a range in window mode', () => {
    const label = scopeLabel(
      { clientId: 2001, programCode: 'GA_JTC', year: 2025, windowMode: true }, OPTIONS, CASCADE,
    );
    expect(label).toContain('TY2020\u20132025');
  });

  it('says so when nothing is priceable', () => {
    const label = scopeLabel(
      { clientId: 2001, programCode: 'SC_JTC', year: 2023, windowMode: false }, OPTIONS, CASCADE,
    );
    expect(label).toContain('no priceable year');
  });

  it('falls back to the account id for an unknown client', () => {
    const label = scopeLabel({ ...initialScope, clientId: 9999, year: 2025 }, OPTIONS, null);
    expect(label).toContain('Account 9999');
  });
});

describe('the portfolio sentinel', () => {
  it('is not a valid account id', () => {
    expect(typeof PORTFOLIO).toBe('string');
    expect(Number.isFinite(Number(PORTFOLIO))).toBe(false);
  });
});

describe('placeholder statute years', () => {
  it('names the years whose floor is a placeholder, for the chosen programme or all', () => {
    const options = { programs: [
      { program_code: 'GA_JTC', placeholder_years: [2026] },
      { program_code: 'SC_JTC', placeholder_years: [] },
    ] };
    expect(placeholderYears(options, 'GA_JTC')).toEqual([2026]);
    expect(placeholderYears(options, 'SC_JTC')).toEqual([]);
    expect(placeholderYears(options, ALL_PROGRAMS)).toEqual([2026]);
    expect(placeholderYears(null, 'GA_JTC')).toEqual([]);
  });
});
