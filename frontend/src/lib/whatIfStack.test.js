import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  addRows, knownPeople, personFor, readSavedStack, readStack, removeToken, setStackStorage,
  subscribe, writeStack,
} from './whatIfStack.js';

function memory() {
  const data = new Map();
  return {
    getItem: (k) => (data.has(k) ? data.get(k) : null),
    setItem: (k, v) => data.set(k, String(v)),
    removeItem: (k) => data.delete(k),
    raw: data,
  };
}

const open = (token, hours = 1, extra = {}) => ({
  record_token: token, employee_id: `E-${token}`, worksite_id: 'GA_GA-016',
  rest_of_year: { state: 'open', additional_weekly_hours: hours }, ...extra,
});

const SCOPE = { clientId: 2001, taxYear: 2026, method: 'min_max' };
let store;

beforeEach(() => { store = memory(); setStackStorage(store); });

describe('the What-if stack across pages (29 Sep)', () => {
  it('adds rows from any page, pre-filled, and never twice', () => {
    expect(addRows(SCOPE, [open('aa', 1.5), open('bb', 2)])).toBe(2);
    expect(addRows(SCOPE, [open('aa', 9)])).toBe(0);
    expect(readStack(SCOPE)).toEqual([
      { token: 'aa', hours: 1.5, raise: 0 },
      { token: 'bb', hours: 2, raise: 0 },
    ]);
  });

  it('keeps tokens and numbers in storage, never an employee id', () => {
    addRows(SCOPE, [open('aa')]);
    const written = [...store.raw.values()].join('');
    expect(written).toContain('aa');
    expect(written).not.toContain('E-aa');
    // Who they are is remembered in memory, for the stack table.
    expect(personFor('aa').employee_id).toBe('E-aa');
    expect(knownPeople().aa.worksite_id).toBe('GA_GA-016');
  });

  it('a row with no rest of the year adds nothing', () => {
    expect(addRows(SCOPE, [{ record_token: 'cc', rest_of_year: { state: 'on_pace' } }])).toBe(0);
    expect(readStack(SCOPE)).toEqual([]);
  });

  it('a stack for another client, year or method is replaced, not mixed', () => {
    addRows(SCOPE, [open('aa')]);
    expect(readStack({ ...SCOPE, taxYear: 2025 })).toEqual([]);
    addRows({ ...SCOPE, method: 'pay_period' }, [open('zz')]);
    expect(readStack(SCOPE)).toEqual([]);
    expect(readSavedStack()).toMatchObject({ clientId: 2001, method: 'pay_period' });
  });

  it('removing the last person clears it, and listeners hear every change', () => {
    const heard = vi.fn();
    const stop = subscribe(heard);
    addRows(SCOPE, [open('aa')]);
    removeToken(SCOPE, 'aa');
    expect(readSavedStack()).toBeNull();
    expect(heard).toHaveBeenCalledTimes(2);
    stop();
    writeStack(SCOPE, []);
    expect(heard).toHaveBeenCalledTimes(2);
  });

  it('survives storage that throws, as in private browsing', () => {
    setStackStorage({ getItem: () => { throw new Error('no'); }, setItem: () => { throw new Error('no'); }, removeItem: () => {} });
    expect(() => addRows(SCOPE, [open('aa')])).not.toThrow();
    expect(readStack(SCOPE)).toEqual([]);
  });
});
