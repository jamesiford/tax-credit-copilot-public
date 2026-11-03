import { describe, expect, it } from 'vitest';
import {
  STEPS, clientSteps, currentStep, stepHref, unavailableReason,
} from './clientFlow.js';
import { methodLabel, rulePackLabel, runLabel } from './reviewMeta.js';

describe('the client review flow', () => {
  it('offers only steps that have somewhere to go, and no Discovery', () => {
    expect(STEPS.map((s) => s.label)).toEqual([
      'Position', 'Eligibility', 'Trend', 'At risk', 'What-if', 'Evidence',
    ]);
  });

  it('takes the current step from the route, never from state of its own', () => {
    expect(currentStep({ view: 'trend', ctab: 'progress' })).toBe('progress');
    expect(currentStep({ view: 'trend' })).toBe('location');
    expect(currentStep({ view: 'eligibility' })).toBe('eligibility');
    expect(currentStep({ view: 'evidence', ctab: 'whatif' })).toBe('evidence');
  });

  it('a section keeps the rest of the query and changes only the question', () => {
    expect(stepHref('progress', { clientId: 2001, search: 'year=2023' })).toBe('/c/2001?year=2023&ctab=progress');
    // The default section carries no ctab, so the URL stays the short one.
    expect(stepHref('location', { clientId: 2001, search: 'ctab=claimed' })).toBe('/c/2001');
  });

  it('a view carries the year and nothing else', () => {
    expect(stepHref('eligibility', { clientId: 2001, year: 2023, search: 'ctab=claimed&wlever=x' }))
      .toBe('/c/2001/eligibility?year=2023');
    expect(stepHref('evidence', { clientId: 2001 })).toBe('/c/2001/evidence');
  });

  it('marks exactly one step current and every step a link', () => {
    const steps = clientSteps({ clientId: 2001, current: 'claimed' });
    expect(steps.filter((s) => s.status === 'current').map((s) => s.id)).toEqual(['claimed']);
    expect(steps.every((s) => typeof s.to === 'string')).toBe(true);
  });

  it('never blocks on a read still in flight', () => {
    expect(unavailableReason(null)).toBeNull();
  });

  it('disables the calculating steps, with the reason, when nothing can be calculated', () => {
    const steps = clientSteps({
      clientId: 9, clientScope: { payroll_years: [2030], calculable_years: [] },
    });
    const byId = Object.fromEntries(steps.map((s) => [s.id, s]));
    expect(byId.location.status).toBe('disabled');
    expect(byId.location.reason).toMatch(/no year overlaps an authored statute/);
    expect(byId.location.to).toBeUndefined();
    // The audit trail reads the certified run, not this client's years.
    expect(byId.evidence.status).toBe('upcoming');
  });

  it('says there is no payroll when there is none', () => {
    expect(unavailableReason({ payroll_years: [], calculable_years: [] })).toMatch(/No payroll is held/);
  });
});

describe('the review header wording', () => {
  it('names a method and says nothing for one it does not know', () => {
    expect(methodLabel('min_max')).toBe('Min-Max');
    expect(methodLabel('pay_period')).toBe('Pay Period');
    expect(methodLabel('x')).toBeNull();
  });

  it('shortens a run id and a rule pack path to what a reader needs', () => {
    expect(runLabel({ run_id: 'abcdef0123456789' })).toBe('abcdef012345');
    expect(runLabel(null)).toBeNull();
    expect(rulePackLabel('rules/ga_jtc/2023.json')).toBe('ga_jtc/2023');
    expect(rulePackLabel('C:\\x\\rules\\ga_jtc\\2023.json')).toBe('ga_jtc/2023');
    expect(rulePackLabel(undefined)).toBeNull();
  });
});
