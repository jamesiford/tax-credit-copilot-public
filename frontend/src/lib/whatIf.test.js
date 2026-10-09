import { describe, expect, it } from 'vitest';
import {
  MAX_STACK, addToStack, clientTab, isWhatIfTarget, jobsShort, parseStack, parseWhatIf, removeFromStack,
  stackEntry, stackPatch, whatIfLink,
} from './whatIf.js';

const below = { tax_year: 2025, status: 'below_minimum', net_new_vs_base: 0.34, threshold: 2, is_base_year: false };
const above = { tax_year: 2025, status: 'above_minimum', net_new_vs_base: 10.59, threshold: 2, is_base_year: false };

describe('jobs short of the minimum', () => {
  it('rounds UP, so the pre-filled hire actually clears the line', () => {
    expect(jobsShort(below)).toBe(2);
    expect(jobsShort({ ...below, net_new_vs_base: 0 })).toBe(2);
    expect(jobsShort({ ...below, net_new_vs_base: 1.5 })).toBe(1);
  });

  it('is zero for a location over the line, and does not turn 2.0000001 into three', () => {
    expect(jobsShort(above)).toBe(0);
    expect(jobsShort({ ...below, net_new_vs_base: -0.0000001 })).toBe(2);
  });
});

describe('which rows open What-if', () => {
  it('only a measured year: never a base year, never a partial one', () => {
    expect(isWhatIfTarget(below)).toBe(true);
    expect(isWhatIfTarget(above)).toBe(true);
    expect(isWhatIfTarget({ ...below, status: 'base', is_base_year: true })).toBe(false);
    expect(isWhatIfTarget({ ...below, status: 'partial' })).toBe(false);
    expect(whatIfLink({ ...below, status: 'partial' }, { unitId: 'GA_GA-016' })).toBeNull();
  });
});

describe('the link a Reading pill applies', () => {
  it('below the minimum: scopes, pre-fills Hire with the jobs short, and runs it', () => {
    expect(whatIfLink(below, { unitId: 'GA_GA-016', method: 'pay_period' })).toEqual({
      ctab: 'whatif', wunit: 'GA_GA-016', wstack: '', wemp: '', wyear: '2025', wmethod: 'pay_period',
      wlever: 'add_headcount', wmag: '2', wrun: '1',
    });
  });

  it('above the minimum: scopes only, because no one lever follows from "fine"', () => {
    const link = whatIfLink(above, { unitId: 'GA_GA-004', method: 'min_max' });
    expect(link).toMatchObject({ ctab: 'whatif', wunit: 'GA_GA-004', wyear: '2025' });
    expect(link.wlever).toBe('');
    expect(link.wrun).toBe('');
  });

  it('round-trips through the URL', () => {
    const search = new URLSearchParams(whatIfLink(below, { unitId: 'GA_GA-016', method: 'min_max' }));
    expect(clientTab(search)).toBe('whatif');
    expect(parseWhatIf(search)).toEqual({
      unitId: 'GA_GA-016', stack: [], year: 2025, method: 'min_max',
      action: 'add_headcount', magnitude: 2, autorun: true,
    });
  });

  it('ignores a lever or tab it does not know rather than passing it through', () => {
    const search = new URLSearchParams({ ctab: 'nonsense', wlever: 'bribe', wmethod: 'vibes' });
    expect(clientTab(search)).toBe('location');
    expect(parseWhatIf(search)).toMatchObject({ action: null, method: 'min_max', unitId: null });
  });
});


describe('the employee stack (28 Sep)', () => {
  const row = (rest, over = {}) => ({ record_token: 'a1b2c3', employee_id: '200100328', rest_of_year: rest, ...over });

  it('a row adds itself pre-filled with what closes its gap: hours, or hours and a raise', () => {
    expect(stackEntry(row({ state: 'open', additional_weekly_hours: 2.87 }))).toEqual({ token: 'a1b2c3', hours: 2.87, raise: 0 });
    expect(stackEntry(row({
      state: 'open', additional_weekly_hours: 9.4, rate_limited: true,
      suggested_additional_weekly_hours: 0.5, suggested_hourly_raise: 3.25,
    }))).toEqual({ token: 'a1b2c3', hours: 0.5, raise: 3.25 });
  });

  it('offers nothing where there is no rest of the year to change', () => {
    for (const state of ['on_pace', 'closed', 'no_payroll_to_date']) {
      expect(stackEntry(row({ state }))).toBeNull();
    }
    expect(stackEntry({ rest_of_year: { state: 'open' } })).toBeNull();
  });

  it('adding keeps what is already there, edits included, and never adds twice', () => {
    const one = { token: 'aa', hours: 1, raise: 0 };
    const edited = { token: 'aa', hours: 7, raise: 2 };
    const two = { token: 'bb', hours: 2, raise: 0 };
    expect(addToStack([edited], [one, two])).toEqual([edited, two]);
    expect(removeFromStack([edited, two], 'aa')).toEqual([two]);
  });

  it('stops at the most one projection stacks', () => {
    const many = Array.from({ length: MAX_STACK + 3 }, (_, i) => ({ token: `t${i}`, hours: 1, raise: 0 }));
    expect(addToStack([], many)).toHaveLength(MAX_STACK);
  });

  it('round-trips through the URL, with record tokens and never an employee id', () => {
    const stack = [{ token: 'aa11', hours: 2.87, raise: 0 }, { token: 'bb22', hours: 0.5, raise: 3.25 }];
    const patch = stackPatch(stack, { taxYear: 2026, method: 'min_max', open: true });
    expect(patch).toMatchObject({ ctab: 'whatif', wstack: 'aa11~2.87~0,bb22~0.5~3.25', wyear: '2026', wrun: '1', wunit: '' });
    const parsed = parseWhatIf(new URLSearchParams(patch));
    expect(parsed).toMatchObject({ stack, year: 2026, method: 'min_max', autorun: true, unitId: null });
    expect(Object.values(stackPatch([{ token: stackEntry(row({ state: 'open', additional_weekly_hours: 1 })).token, hours: 1, raise: 0 }], { taxYear: 2026 })).join('|'))
      .not.toContain('200100328');
  });

  it('adding without opening does not switch tab or run', () => {
    const patch = stackPatch([{ token: 'aa', hours: 1, raise: 0 }], { taxYear: 2026, method: 'min_max' });
    expect(patch.ctab).toBeUndefined();
    expect(patch.wrun).toBe('');
  });

  it('drops malformed, repeated and out-of-range entries rather than passing them through', () => {
    expect(parseStack('aa~1~0,aa~2~0,bad token~1~0,~1~1,bb~-3~500')).toEqual([
      { token: 'aa', hours: 1, raise: 0 },
      { token: 'bb', hours: 0, raise: 100 },
    ]);
  });

  it('reads a pre-stack employee link as a stack of one', () => {
    const parsed = parseWhatIf(new URLSearchParams({ wemp: 'tok123', wmag: '2.87', wyear: '2025', wrun: '1' }));
    expect(parsed.stack).toEqual([{ token: 'tok123', hours: 2.87, raise: 0 }]);
  });
});
describe('an open year (TY2026)', () => {
  const behind = { tax_year: 2026, status: 'in_progress', qualified: false, net_new_vs_base: 0.4, threshold: 2, is_base_year: false };

  it('is a what-if target: it is the one year still movable', () => {
    expect(isWhatIfTarget(behind)).toBe(true);
  });

  it('behind pace pre-fills the hires it is short and runs; on track only scopes', () => {
    expect(whatIfLink(behind, { unitId: 'GA_GA-016' })).toMatchObject({ wyear: '2026', wlever: 'add_headcount', wmag: '2', wrun: '1' });
    expect(whatIfLink({ ...behind, qualified: true, net_new_vs_base: 5 }, { unitId: 'GA_GA-016' }))
      .toMatchObject({ wyear: '2026', wlever: '', wmag: '', wrun: '' });
  });
});

describe('jobs short, below the base', () => {
  it('counts the whole shortfall, not just the minimum, when the row carries its base', () => {
    const row = { status: 'in_progress', qualified: false, threshold: 2, net_new_vs_base: 0, average_headcount: 3, base_average_headcount: 7.33 };
    expect(jobsShort(row)).toBe(7);
    expect(jobsShort({ ...row, average_headcount: 7.67 })).toBe(2);
  });
});
