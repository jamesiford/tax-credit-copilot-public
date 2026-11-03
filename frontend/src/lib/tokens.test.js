/**
 * Token integrity and the deprecated-alias ratchet.
 *
 * Two promises:
 *
 *   1. Every token a token file references is declared somewhere, and every
 *      deprecated alias still resolves. An alias that points at a name nobody
 *      declares is a `var()` that silently computes to nothing — the failure
 *      this stylesheet already suffered once, when 53 declarations were dead.
 *
 *   2. The deprecated vocabulary (`--accent*`, `--accent-2*`, `--exp-*`) may
 *      only shrink. The counts below are a ratchet: lowering one is the point
 *      of a migration and is committed with it; raising one fails the build.
 *      New code reads the role (`--reading*`, `--select*`, `--identity-*`).
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

// Vitest runs from the frontend package root (jsdom gives `import.meta.url` an
// http scheme, so it cannot locate the files).
const SRC = join(process.cwd(), 'src');
const TOKENS = join(SRC, 'styles', 'tokens');

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

const read = (path) => readFileSync(path, 'utf8');
const stripComments = (css) => css.replace(/\/\*[\s\S]*?\*\//g, '');

const tokenFiles = walk(TOKENS).filter((p) => p.endsWith('.css'));
const sourceFiles = walk(SRC).filter(
  (p) => /\.(css|jsx)$/.test(p) && !/\.test\./.test(p) && !p.startsWith(TOKENS),
);

const declared = new Set();
for (const file of [...tokenFiles, ...sourceFiles.filter((p) => p.endsWith('.css'))]) {
  for (const [, name] of stripComments(read(file)).matchAll(/(--[\w-]+)\s*:/g)) declared.add(name);
}

/** Names a `var()` reaches for WITHOUT a fallback: those must be declared. */
function unfallbacked(text) {
  return [...stripComments(text).matchAll(/var\((--[\w-]+)\s*\)/g)].map((m) => m[1]);
}

const DEPRECATED = [
  /^--accent(-strong|-bg)?$/,
  /^--accent-2(-strong|-bg|-line)?$/,
  /^--exp-[\w-]+$/,
];

function countDeprecated() {
  const counts = {};
  for (const file of sourceFiles) {
    const text = stripComments(read(file));
    for (const [, name] of text.matchAll(/var\((--[\w-]+)/g)) {
      if (DEPRECATED.some((rule) => rule.test(name))) counts[name] = (counts[name] || 0) + 1;
    }
  }
  return counts;
}

// The ratchet. Measured at the start of UI-01 and shrunk by every prompt since;
// at 0 no component reads a deprecated alias. The aliases still RESOLVE (a customer
// overlay written against them keeps working), they are just never read here.
const CEILING = {
  '--exp-primary': 0,
  '--exp-accent': 0,
  '--exp-magenta': 0,
  '--exp-subtle-2': 0,
  '--exp-muted': 0,
  '--exp-blue': 0,
  '--exp-subtle': 0,
  '--exp-ink': 0,
  '--exp-gold': 0,
  '--exp-violet': 0,
  '--accent': 0,
  '--accent-strong': 0,
  '--accent-bg': 0,
  '--accent-2': 0,
  '--accent-2-strong': 0,
  '--accent-2-bg': 0,
  '--accent-2-line': 0,
};

describe('token files', () => {
  it('only reference tokens that are declared', () => {
    const missing = [];
    for (const file of tokenFiles) {
      for (const name of unfallbacked(read(file))) {
        if (!declared.has(name)) missing.push(`${relative(SRC, file)} -> ${name}`);
      }
    }
    expect(missing).toEqual([]);
  });

  it('keep every deprecated alias defined, so nothing silently computes to nothing', () => {
    for (const name of Object.keys(CEILING)) expect(declared.has(name)).toBe(true);
  });

  it('declare every --state-* family with ink and line, each aliasing a status role', () => {
    const state = stripComments(read(join(TOKENS, 'state.css')));
    for (const family of ['base-year', 'above-min', 'below-min', 'partial', 'neutral']) {
      for (const suffix of ['', '-ink', '-line']) {
        const match = state.match(new RegExp(`--state-${family}${suffix}:\\s*([^;]+);`));
        expect(match, `--state-${family}${suffix}`).not.toBeNull();
        expect(match[1].trim()).toMatch(/^var\(--status-[\w-]+\)$/);
      }
    }
  });

  it('keep literals out of state.css', () => {
    expect(stripComments(read(join(TOKENS, 'state.css')))).not.toMatch(/#[0-9a-f]{3,8}\b|rgba?\(/i);
  });

  it('are assigned by both themes for every semantic role the modern theme assigns', () => {
    const roles = (file, selector) => {
      const css = stripComments(read(join(TOKENS, file)));
      const block = css.split(selector)[1]?.split('\n}')[0] ?? '';
      return new Set([...block.matchAll(/(--[\w-]+)\s*:/g)].map((m) => m[1]));
    };
    const modern = roles('theme-modern.css', 'html[data-theme="modern"] {');
    const classic = roles('theme-classic.css', 'html[data-theme="classic"] {');
    // `--font-data` and the leading tokens are theme-valued too.
    const absent = [...modern].filter((name) => !classic.has(name));
    expect(absent).toEqual([]);
  });
});

describe('the deprecated alias ratchet', () => {
  const counts = countDeprecated();

  it('never grows', () => {
    const grown = Object.entries(counts)
      .filter(([name, n]) => n > (CEILING[name] ?? 0))
      .map(([name, n]) => `${name}: ${n} > ${CEILING[name] ?? 0}`);
    expect(grown).toEqual([]);
  });

  it('is pinned at its measured value, so a shrink is committed with its migration', () => {
    const slack = Object.entries(CEILING)
      .filter(([name, n]) => (counts[name] ?? 0) < n)
      .map(([name, n]) => `${name}: now ${counts[name] ?? 0}, ceiling ${n} — lower the ceiling`);
    expect(slack).toEqual([]);
  });
});
