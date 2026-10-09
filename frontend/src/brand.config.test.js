import { describe, expect, it } from 'vitest';
import { brand } from './brand.config.js';

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
