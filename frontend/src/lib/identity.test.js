import { describe, expect, it } from 'vitest';
import { firstName, greeting, initials } from './identity.js';

const signedIn = (upn) => ({ authenticated: true, upn, auth_mode: 'entra' });

describe('greeting the person, not guessing at them', () => {
  it('says Hi, <first name> when signed in', () => {
    expect(greeting(signedIn('jane.doe@example.com'))).toBe('Hi, Jane');
    expect(firstName(signedIn('analyst@example.com'))).toBe('Analyst');
  });

  it('says Welcome back when nobody is signed in', () => {
    expect(greeting({ authenticated: false, upn: null, auth_mode: 'none' })).toBe('Welcome back');
    expect(greeting(null)).toBe('Welcome back');
    expect(greeting(undefined)).toBe('Welcome back');
  });

  it('does not greet by a local part that is not a name', () => {
    expect(firstName(signedIn('x@example.com'))).toBeNull();
    expect(firstName(signedIn('1234@example.com'))).toBeNull();
    expect(greeting(signedIn('x@example.com'))).toBe('Welcome back');
  });

  it('ignores a UPN on an unauthenticated identity', () => {
    expect(firstName({ authenticated: false, upn: 'jane@example.com' })).toBeNull();
  });
});

describe('initials', () => {
  it('uses the first letter of the first two name parts', () => {
    expect(initials(signedIn('jane.doe@example.com'))).toBe('JD');
  });

  it('falls back to the first two letters of a single word', () => {
    expect(initials(signedIn('analyst@example.com'))).toBe('AN');
  });

  it('is empty when there is no identity', () => {
    expect(initials(null)).toBe('');
  });
});
