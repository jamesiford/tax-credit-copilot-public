import { describe, expect, it } from 'vitest';
import { programVerdict } from './programVerdict.js';

const RULE = { code: 'GA_JTC', name: 'GA job tax credit', jurisdiction: 'GA', verified: false };

describe('a programme verdict', () => {
  it('is calculable when a year pack is authored, and says which years', () => {
    const v = programVerdict(RULE, [2019, 2020, 2021]);
    expect(v.tone).toBe('above-min');
    expect(v.pills.map((p) => p.label)).toEqual(['GA', 'Calculable', 'Review pending']);
    expect(v.assessment).toMatch(/authored for/);
  });

  it('is not calculated, and says it will not borrow a neighbour, when none is', () => {
    const v = programVerdict(RULE, []);
    expect(v.tone).toBe('partial');
    expect(v.assessment).toMatch(/neighbouring year/);
  });

  it('makes no readiness claim when the authored years are unknown', () => {
    const v = programVerdict(RULE, [], false);
    expect(v.tone).toBe('neutral');
    expect(v.assessment).toBeNull();
    expect(v.pills.map((p) => p.label)).toEqual(['GA', 'Review pending']);
  });

  it('keeps sign-off separate from readiness', () => {
    const v = programVerdict({ ...RULE, verified: true }, []);
    expect(v.pills.at(-1)).toMatchObject({ label: 'Signed off', variant: 'above-min' });
    expect(v.tone).toBe('partial');
  });

  it('never uses the selection blue (base-year) for a verdict', () => {
    for (const years of [[], [2020]]) {
      expect(programVerdict(RULE, years).pills.some((p) => p.variant === 'base-year')).toBe(false);
    }
  });
});
