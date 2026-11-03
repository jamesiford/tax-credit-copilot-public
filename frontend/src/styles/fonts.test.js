/**
 * The type is self-hosted and woff2-only, and nothing can quietly undo that.
 *
 * `@fontsource/<family>/<weight>.css` declares a woff2 AND a woff, so importing
 * it ships both of every face. `fonts.css` declares only woff2, and each family
 * carries a metric-matched fallback so the swap does not move the layout.
 */
import { describe, expect, it } from 'vitest';
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const src = resolve(here, '..');
const fontsCss = readFileSync(join(here, 'fonts.css'), 'utf8');

function sourceFiles(dir) {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return sourceFiles(full);
    return /\.(jsx?|css)$/.test(name) && !/\.test\./.test(name) ? [full] : [];
  });
}

describe('self-hosted fonts', () => {
  it('imports no @fontsource stylesheet, which would add the woff duplicates', () => {
    const offenders = sourceFiles(src).filter((file) => {
      const text = readFileSync(file, 'utf8');
      return /@fontsource\/[\w-]+\/[^'"]*\.css|import\s+['"]@fontsource\//.test(text);
    });
    expect(offenders).toEqual([]);
  });

  it('declares woff2 and nothing else', () => {
    const urls = [...fontsCss.matchAll(/url\(([^)]+)\)/g)].map((m) => m[1].replace(/['"]/g, ''));
    expect(urls.length).toBeGreaterThan(0);
    for (const url of urls) expect(url).toMatch(/\.woff2$/);
    expect(fontsCss).not.toMatch(/format\(['"]woff['"]\)/);
  });

  it('points every face at a file that exists', () => {
    const urls = [...fontsCss.matchAll(/url\(([^)]+)\)/g)].map((m) => m[1].replace(/['"]/g, ''));
    for (const url of urls) expect(existsSync(resolve(here, url)), url).toBe(true);
  });

  it('gives each family a metric-matched fallback, so the swap does not shift layout', () => {
    for (const family of ['Poppins Fallback', 'Roboto Fallback']) {
      const block = fontsCss.split('@font-face').find((b) => b.includes(`'${family}'`) || b.includes(`"${family}"`));
      expect(block, family).toBeTruthy();
      for (const descriptor of ['size-adjust', 'ascent-override', 'descent-override', 'line-gap-override']) {
        expect(block, `${family} ${descriptor}`).toContain(descriptor);
      }
    }
  });

  it('uses font-display: swap on every real face', () => {
    const faces = fontsCss.split('@font-face').slice(1).filter((b) => b.includes('url('));
    for (const face of faces) expect(face).toContain('font-display: swap');
  });
});
