import { describe, expect, it } from 'vitest';
import {
  NOT_VERIFIED, PACK_FIELDS, PREVIEW_LABEL, STATUTE_WARNING, YEAR_FIELDS, coerce, engagementLabel, fieldFinding, getIn, lifecycleLabel,
  parseDocument, programsInStateOf, saveBlocked, setIn, slashPath, stepStates, unverifiedLabel, validationSummary, yearSkeleton, yearsLabel,
} from './programs.js';

describe('the words that cannot be softened', () => {
  it('never claims verification and says what is needed', () => {
    expect(NOT_VERIFIED).toBe('Not verified');
    expect(STATUTE_WARNING).toMatch(/unverified until a person verifies/);
    expect(STATUTE_WARNING).toMatch(/not legally correct/);
    expect(PREVIEW_LABEL).toBe('Preview, not verified, not for filing');
  });

  it('states the verification of a catalog row as not verified, with the flagged years', () => {
    expect(unverifiedLabel({ authored_years: [2024, 2025], unverified_years: [2025] })).toBe('Not verified: 1 of 2 years flagged');
    expect(unverifiedLabel({ authored_years: [], unverified_years: [] })).toBe('Not verified');
    expect(unverifiedLabel({ authored_years: [2024], unverified_years: [] })).toMatch(/^Not verified/);
  });
});

describe('catalog labels', () => {
  it('compresses authored years into ranges and says when there are none', () => {
    expect(yearsLabel([2019, 2020, 2021, 2023])).toBe('2019\u20132021, 2023');
    expect(yearsLabel([])).toBe('none authored');
  });

  it('labels lifecycles and engagement without inventing a count', () => {
    expect(lifecycleLabel({ lifecycle: 'described' })).toBe('Described, not calculable');
    expect(engagementLabel(null)).toBe('Unavailable');
    expect(engagementLabel({ clients: 0 })).toBe('No clients');
    expect(engagementLabel({ clients: 3, in_scope: 1 })).toBe('3 clients (1 in scope)');
  });

  it('finds the programs already registered for a state, case-insensitively', () => {
    const rows = [{ code: 'A', state: 'ZZ' }, { code: 'B', state: 'GA' }, { code: 'C', state: 'zz' }];
    expect(programsInStateOf(rows, 'zz').map((r) => r.code)).toEqual(['A', 'C']);
    expect(programsInStateOf(rows, '')).toEqual([]);
  });
});

describe('the workflow steps', () => {
  it('disables every step but the first until a draft exists, each with its reason', () => {
    const steps = stepStates(null, 'basics');
    expect(steps.map((s) => s.status)).toEqual(['current', 'disabled', 'disabled', 'disabled', 'disabled', 'disabled']);
    expect(steps[1].reason).toMatch(/Create the draft/);
  });

  it('holds preview until a year exists and export until the review approved it', () => {
    const draft = { status: 'draft', documents: { pack: {}, years: {} } };
    expect(stepStates(draft, 'pack').find((s) => s.id === 'preview').reason).toMatch(/Add a tax year/);
    expect(stepStates(draft, 'pack').find((s) => s.id === 'export').reason).toMatch(/approved review/);
    const ready = { status: 'approved_for_export', documents: { pack: {}, years: { 2025: {} } } };
    const states = stepStates(ready, 'pack');
    expect(states.find((s) => s.id === 'preview').status).toBe('upcoming');
    expect(states.find((s) => s.id === 'export').status).toBe('upcoming');
    expect(states.find((s) => s.id === 'pack').status).toBe('current');
    expect(stepStates(ready, 'review').find((s) => s.id === 'preview').status).toBe('done');
  });

  it('blocks editing once the draft is under review', () => {
    expect(saveBlocked({ status: 'draft' })).toBeNull();
    expect(saveBlocked({ status: 'ready_for_review' })).toMatch(/cannot be edited/);
  });
});

describe('editing documents', () => {
  it('sets a nested value immutably', () => {
    const before = { credit: { name: 'a' } };
    const after = setIn(before, 'benefit.amount_per_qualifying_job_usd', 5);
    expect(after.benefit.amount_per_qualifying_job_usd).toBe(5);
    expect(before).toEqual({ credit: { name: 'a' } });
    expect(getIn(after, 'benefit.amount_per_qualifying_job_usd')).toBe(5);
  });

  it('stores an empty field as null and a number as a number, never a guess', () => {
    const number = PACK_FIELDS.find((f) => f.number);
    expect(coerce(number, '')).toBeNull();
    expect(coerce(number, ' 12.5 ')).toBe(12.5);
    expect(coerce(PACK_FIELDS[0], '  Name ')).toBe('Name');
  });

  it('starts a year from an empty flagged skeleton that copies no value from the base pack', () => {
    const pack = { credit: { code: 'ZZ_X', name: 'X' }, jurisdiction: { level: 'state', code: 'ZZ', name: 'Z' }, thresholds: { minimum_new_jobs: 7 } };
    const year = yearSkeleton(pack, 2026);
    expect(year.tax_year).toBe(2026);
    expect(year.thresholds.minimum_new_jobs).toBeNull();
    expect(year.thresholds._prototype_verify).toBe(true);
    expect(year.credit.code).toBe('ZZ_X');
    expect(year._year_provenance.source).toMatch(/^TODO/);
  });

  it('offers a provenance source field for a year and a citation field for the pack', () => {
    expect(YEAR_FIELDS[0].path).toBe('_year_provenance.source');
    expect(PACK_FIELDS.find((f) => f.path === 'credit.statutory_citation').cite).toBe(true);
  });

  it('parses the advanced editor text and says why it cannot', () => {
    expect(parseDocument('{"a":1}')).toEqual({ ok: true, value: { a: 1 } });
    expect(parseDocument('[1]').ok).toBe(false);
    expect(parseDocument('{').error).toMatch(/Not valid JSON/);
  });
});

describe('validation findings', () => {
  const validation = {
    valid: false, errors: 1, infos: 2,
    findings: [
      { file: 'pack', severity: 'info', code: 'unverified', path: 'thresholds', message: 'flag' },
      { file: 'pack', severity: 'error', code: 'schema', path: 'thresholds/minimum_new_jobs', message: 'is not a number' },
    ],
  };

  it('addresses a finding to a dotted field path and prefers the error', () => {
    expect(slashPath('thresholds.minimum_new_jobs')).toBe('thresholds/minimum_new_jobs');
    expect(fieldFinding(validation, 'pack', 'thresholds.minimum_new_jobs').message).toBe('is not a number');
    expect(fieldFinding(validation, 'pack', 'thresholds')).toBeNull(); // information is listed in the panel, not on the field
    expect(fieldFinding(validation, 'year 2025', 'thresholds.minimum_new_jobs')).toBeNull();
  });

  it('summarises a pass as valid but not verified', () => {
    expect(validationSummary(null)).toBe('Not validated yet');
    expect(validationSummary({ valid: true, infos: 3 })).toMatch(/valid is not verified/);
    expect(validationSummary(validation)).toBe('1 error to fix');
  });
});
