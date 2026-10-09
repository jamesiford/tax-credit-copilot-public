import { describe, expect, it } from 'vitest';
import { assumptionEntries, authoredYearsLabel, eligibilityLabel, monthLabel, shortHash, SOURCE_FIELD_MAP, stageLabel, statusTone } from './reference.js';

describe('Reference workspace presentation helpers', () => {
  it('shortens reproducibility hashes without retaining the prefix', () => {
    expect(shortHash('sha256:abcdef1234567890')).toBe('abcdef123456…');
    expect(shortHash(null)).toBe('—');
  });

  it('labels method eligibility differences honestly', () => {
    expect(eligibilityLabel('both')).toBe('Eligible in both');
    expect(eligibilityLabel('min_max_only')).toBe('Min-Max only');
    expect(eligibilityLabel('pay_period_only')).toBe('Pay Period only');
    expect(eligibilityLabel('neither')).toBe('Not eligible');
  });

  it('maps statuses to non-color semantic tones', () => {
    expect(statusTone('complete')).toBe('ok');
    expect(statusTone('awaiting_outputs')).toBe('warn');
    expect(statusTone('unknown')).toBe('neutral');
  });

  it('formats stage and month labels', () => {
    expect(stageLabel('common_employee_totals')).toBe('Common Employee Totals');
    expect(monthLabel('2023-08-31')).toBe('Aug 23');
  });

  it('turns assumption maps into stable display rows', () => {
    expect(assumptionEntries({ assumptions: { 'BA-01': { status: 'approved' } } })).toEqual([
      { id: 'BA-01', status: 'approved' },
    ]);
  });

  it('says authored years as ranges and keeps a gap visible', () => {
    expect(authoredYearsLabel([2021, 2019, 2020, 2022, 2023, 2024, 2025])).toBe('2019\u20132025');
    expect(authoredYearsLabel([2019, 2020, 2022])).toBe('2019\u20132020, 2022');
    expect(authoredYearsLabel([2025])).toBe('2025');
    expect(authoredYearsLabel([])).toBeNull();
    expect(authoredYearsLabel(undefined)).toBeNull();
  });

  it('defines the complete TCC source contract without synthetic fields', () => {
    expect(SOURCE_FIELD_MAP).toHaveLength(11);
    expect(SOURCE_FIELD_MAP.map((field) => field.source)).toContain('TCCEmployeeId');
    expect(SOURCE_FIELD_MAP.map((field) => field.source)).not.toContain('LocationState');
  });
});
