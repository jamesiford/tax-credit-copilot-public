import { describe, expect, it } from 'vitest';
import { kpiTone } from './kpiTone.js';

describe('kpiTone', () => {
  it('maps the old colour names onto state families', () => {
    expect(kpiTone('green')).toBe('above-min');
    expect(kpiTone('amber')).toBe('partial');
    expect(kpiTone('red')).toBe('below-min');
  });

  it('treats anything else, including the readingless "accent", as neutral', () => {
    expect(kpiTone('accent')).toBe('neutral');
    expect(kpiTone('')).toBe('neutral');
    expect(kpiTone(undefined)).toBe('neutral');
  });
});
