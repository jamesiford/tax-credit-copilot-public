import { describe, expect, it } from 'vitest';
import { calculablePrograms, chosenProgram, hasSeveralPrograms, programName, programsInState } from './programChoice.js';

const p = (code, state, years = [2024], over = {}) => ({
  program_code: code, name: `${code} name`, authored_years: years, jurisdiction: { code: state, level: 'state' }, ...over,
});
const options = {
  programs: [
    p('GA_JTC', 'GA', [2024, 2025]), p('ZZ_ALPHA', 'ZZ'), p('ZZ_BETA', 'ZZ'),
    p('ZZ_DESCRIBED', 'ZZ', []), p('FED_X', '', [2024], { jurisdiction: { code: '', level: 'federal' } }),
  ],
};

describe('which program a run is for', () => {
  it('lists only programs the engine can price: authored statute and a state', () => {
    expect(calculablePrograms(options).map((x) => x.program_code)).toEqual(['GA_JTC', 'ZZ_ALPHA', 'ZZ_BETA']);
  });

  it('keeps registry order within a state, so the first is the default', () => {
    expect(programsInState(options, 'zz').map((x) => x.program_code)).toEqual(['ZZ_ALPHA', 'ZZ_BETA']);
    expect(programsInState(options, 'TX')).toEqual([]);
  });

  it('asks for a program only where a state holds several', () => {
    expect(hasSeveralPrograms(options, 'ZZ')).toBe(true);
    expect(hasSeveralPrograms(options, 'GA')).toBe(false);
  });

  it('sends nothing for a single-program state, so those controls call exactly as before', () => {
    expect(chosenProgram(options, 'GA', 'GA_JTC', 'GA_JTC')).toBeNull();
  });

  it('prefers the pick, then the scope program, then the first of the state, and ignores a program of another state', () => {
    expect(chosenProgram(options, 'ZZ', null, 'ZZ_BETA')).toBe('ZZ_BETA');
    expect(chosenProgram(options, 'ZZ', 'ZZ_BETA', '')).toBe('ZZ_BETA');
    expect(chosenProgram(options, 'ZZ', 'GA_JTC', '')).toBe('ZZ_ALPHA');
    expect(chosenProgram(options, 'ZZ', null, 'GA_JTC')).toBe('ZZ_ALPHA');
  });

  it('names a program by code when two share a state', () => {
    expect(programName(p('ZZ_ALPHA', 'ZZ'))).toBe('ZZ_ALPHA name (ZZ_ALPHA)');
    expect(programName({ program_code: 'X', name: 'X' })).toBe('X');
  });
});
