import { afterEach, describe, expect, it } from 'vitest';
import { loadStartHere, START_HERE_KEY, storeStartHere } from './startHere.js';

afterEach(() => window.localStorage.clear());

describe('Start here', () => {
  it('is expanded on a first visit', () => {
    expect(loadStartHere()).toBe(true);
  });

  it('remembers a collapse, and an expand', () => {
    storeStartHere(false);
    expect(window.localStorage.getItem(START_HERE_KEY)).toBe('collapsed');
    expect(loadStartHere()).toBe(false);
    storeStartHere(true);
    expect(loadStartHere()).toBe(true);
  });

  it('survives storage that throws', () => {
    const blocked = {
      getItem: () => { throw new Error('blocked'); },
      setItem: () => { throw new Error('blocked'); },
    };
    expect(loadStartHere(blocked)).toBe(true);
    expect(() => storeStartHere(false, blocked)).not.toThrow();
  });
});
