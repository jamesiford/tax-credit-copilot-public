import { describe, expect, it } from 'vitest';
import { applyTheme, brand, configuredTheme, THEME_STORAGE_KEY } from './brand.config.js';

// The default brand is neutral, and every field is overridable at build time
// through a VITE_BRAND_* variable (see overlays/README.md). [WL-1]
describe('brand.config', () => {
  it('defaults to the neutral Tax Credit Copilot brand', () => {
    expect(brand.name).toBe('Tax Credit Copilot');
    expect(brand.shortName).toBe('TCC');
    expect(brand.logoSrc).toBe('/brand-mark.svg');
    expect(brand.faviconSrc).toBe('/brand-mark.svg');
  });
});

describe('theme', () => {
  const store = (value) => ({ getItem: (key) => (key === THEME_STORAGE_KEY ? value : null) });

  it('defaults to the modern theme', () => {
    expect(configuredTheme()).toBe('modern');
  });

  it('sets data-theme on the root before first paint', () => {
    const root = document.createElement('html');
    expect(applyTheme(root, store(null))).toBe('modern');
    expect(root.getAttribute('data-theme')).toBe('modern');
  });

  it('lets a stored choice outrank the build default, and ignores anything unknown', () => {
    const root = document.createElement('html');
    expect(applyTheme(root, store('classic'))).toBe('classic');
    expect(root.getAttribute('data-theme')).toBe('classic');
    expect(applyTheme(root, store('neon'))).toBe('modern');
  });

  it('survives storage that throws', () => {
    const root = document.createElement('html');
    const blocked = { getItem: () => { throw new Error('blocked'); } };
    expect(applyTheme(root, blocked)).toBe('modern');
  });
});
