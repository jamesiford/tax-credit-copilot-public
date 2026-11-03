/**
 * The floating Ask pill must never cover content.
 *
 * It is fixed at the bottom right, so on a long page the last rows would sit
 * under it. The scroll area (`.tcc-main`) therefore reserves bottom padding of
 * at least the pill's height plus its offset, in BOTH themes. This reads the
 * stylesheets rather than a browser, so it holds in CI; `tools/check_states.py`
 * measures the same thing against the rendered page.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = resolve(__dirname, '..', '..');
const read = (path) => readFileSync(resolve(root, path), 'utf8');

const scales = read('styles/tokens/scales.css');
const token = (name) => {
  const match = scales.match(new RegExp(`--${name}:\\s*(\\d+)px`));
  if (!match) throw new Error(`--${name} is not a px value in scales.css`);
  return Number(match[1]);
};

describe('the floating launcher clears the content', () => {
  const offset = token('space-10'); // --floating-offset: var(--space-10)
  // padding (--space-5 top and bottom) around one line of body text.
  const pill = token('space-5') * 2 + 14 * 1.5;
  const reserved = token('space-16') + offset;

  it('reserves at least the pill\u2019s height plus its offset', () => {
    expect(reserved).toBeGreaterThanOrEqual(pill + offset);
  });

  it('every stylesheet that sets the page\u2019s bottom padding uses that reservation', () => {
    for (const file of ['index.css', 'styles/chrome-modern.css']) {
      expect(read(file)).toMatch(
        /\.tcc-main\s*\{[^}]*padding:[^;}]*calc\(var\(--space-16\)\s*\+\s*var\(--floating-offset\)\)/,
      );
    }
  });

  it('the offset is the one token, so the pill and the padding cannot drift', () => {
    expect(scales).toMatch(/--floating-offset:\s*var\(--space-10\)/);
    expect(read('components/ui/FloatingAction.css')).toMatch(/inset-block-end:\s*var\(--floating-offset\)/);
  });
});
