import { describe, expect, it } from 'vitest';
import { atPortfolio, drillRungs } from './drill.js';

const state = (rungs) => Object.fromEntries(rungs.map((r) => [r.key, [r.reached, r.current]]));

describe('the drill is derived from the route', () => {
  it('at the book: only Portfolio is reached, and it is current', () => {
    const rungs = drillRungs({ clientId: 'portfolio', view: 'trend' });
    expect(state(rungs)).toEqual({
      portfolio: [true, true], client: [false, false], unit: [false, false],
      eligibility: [false, false], employee: [false, false],
    });
    expect(atPortfolio(rungs)).toBe(true);
  });

  it('at a client: the rung shows the REAL name, not the word Client', () => {
    const rungs = drillRungs({ clientId: 2002, clientName: 'Ironbridge Logistics', view: 'trend' });
    expect(rungs[1].label).toBe('Ironbridge Logistics');
    expect(state(rungs).client).toEqual([true, true]);
    expect(state(rungs).portfolio).toEqual([true, false]);
    expect(atPortfolio(rungs)).toBe(false);
  });

  it('falls back to the account number before a name has loaded', () => {
    expect(drillRungs({ clientId: 2002, view: 'trend' })[1].label).toBe('Account 2002');
  });

  it('at a location: the unit is current and shows its own id', () => {
    const rungs = drillRungs({ clientId: 2001, clientName: 'Cascade', unitId: 'GA_GA-010', view: 'trend' });
    expect(rungs[2].label).toBe('GA_GA-010');
    expect(state(rungs).unit).toEqual([true, true]);
    expect(state(rungs).client).toEqual([true, false]);
  });

  it('on Eligibility: it is current and the client rung is no longer', () => {
    const rungs = drillRungs({ clientId: 2001, view: 'eligibility' });
    expect(state(rungs).eligibility).toEqual([true, true]);
    expect(state(rungs).client).toEqual([true, false]);
    expect(state(rungs).portfolio).toEqual([true, false]);
  });

  it('Eligibility is NOT reached until a client is: pick a client first', () => {
    const rungs = drillRungs({ clientId: 'portfolio', view: 'trend' });
    expect(rungs[3].reached).toBe(false);
    expect(rungs[3].hint).toBe('pick a client first');
  });

  it('on an employee walk: the employee is current, the unit is not', () => {
    const rungs = drillRungs({ clientId: 2001, unitId: 'GA_GA-010', token: 'abc', view: 'trend' });
    expect(state(rungs).employee).toEqual([true, true]);
    expect(state(rungs).unit[1]).toBe(false);
    expect(state(rungs).client[1]).toBe(false);
  });

  it('every unreached rung says what to do next', () => {
    for (const rung of drillRungs({ clientId: 'portfolio', view: 'trend' })) {
      if (!rung.reached) expect(rung.hint?.length).toBeGreaterThan(0);
    }
  });

  it('exactly one rung is current in every state', () => {
    const cases = [
      { clientId: 'portfolio', view: 'trend' },
      { clientId: 1, view: 'trend' },
      { clientId: 1, unitId: 'u', view: 'trend' },
      { clientId: 1, view: 'eligibility' },
      { clientId: 1, unitId: 'u', token: 't', view: 'trend' },
    ];
    for (const route of cases) {
      expect(drillRungs(route).filter((r) => r.current)).toHaveLength(1);
    }
  });
});
