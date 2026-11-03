/**
 * Dead CSS finder. Dev tooling, not shipped.
 *
 *   node tools/dead_css.mjs           # report selectors no source file can match
 *   node tools/dead_css.mjs --write   # remove them from index.css
 *
 * A selector is DEAD when it needs a class that appears nowhere in `src/`
 * (components, pages, lib; tests excluded: a test pinning a class that no
 * component renders is pinning nothing) and is not the prefix of a class built
 * at run time (`tcc-band-${tone}`). A rule is removed only when EVERY selector in
 * it is dead, so a shared rule keeps living for whoever still uses it.
 *
 * Conservative on purpose: a selector with :not(), :is(), :where() or :has() is
 * kept, as are @keyframes, @font-face and anything inside @media print. A class
 * that is only ever rendered by a third-party library is allow-listed below.
 */
import { readFileSync, writeFileSync, readdirSync, statSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import postcss from 'postcss';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'src');
const target = join(root, 'index.css');
const write = process.argv.includes('--write');

// Classes drawn by libraries, not by our components.
const LIBRARY = [/^u-/, /^lucide/, /^rsm-/, /^recharts-/, /^sr-only$/, /^not-sr-only$/];

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) walk(path, out);
    else if (/\.(jsx?|html)$/.test(name) && !/\.test\./.test(name)) out.push(path);
  }
  return out;
}

const sources = walk(root).map((f) => readFileSync(f, 'utf8')).join('\n')
  + readFileSync(join(root, '..', 'index.html'), 'utf8');

// Prefixes of class names built at run time.
const prefixes = new Set();
for (const m of sources.matchAll(/([A-Za-z0-9_-]+-)\$\{/g)) prefixes.add(m[1]);
for (const m of sources.matchAll(/['"`]([A-Za-z0-9_-]+-)['"`]\s*\+/g)) prefixes.add(m[1]);

const used = (cls) => sources.includes(cls)
  || [...prefixes].some((p) => cls.startsWith(p))
  || LIBRARY.some((re) => re.test(cls));

const classesOf = (selector) => [...selector.matchAll(/\.(-?[_a-zA-Z][\w-]*)/g)].map((m) => m[1]);
const opaque = (selector) => /:(not|is|where|has)\(/.test(selector);

const css = readFileSync(target, 'utf8');
const ast = postcss.parse(css);
const dead = [];

ast.walkRules((rule) => {
  const parent = rule.parent;
  if (parent?.type === 'atrule' && /keyframes|font-face/.test(parent.name)) return;
  if (parent?.type === 'atrule' && parent.name === 'media' && /print/.test(parent.params)) return;
  const verdicts = rule.selectors.map((s) => {
    if (opaque(s)) return { s, dead: false };
    const gone = classesOf(s).filter((c) => !used(c));
    return { s, dead: gone.length > 0, gone };
  });
  if (verdicts.length && verdicts.every((v) => v.dead)) {
    dead.push({ line: rule.source.start.line, selector: rule.selector.replace(/\s+/g, ' ').slice(0, 110), rule });
  }
});

for (const d of dead) console.log(`${String(d.line).padStart(5)}  ${d.selector}`);
console.log(`\n${dead.length} dead rule(s) in index.css`);

if (write) {
  for (const d of dead) d.rule.remove();
  // A media block emptied by the removals goes too.
  ast.walkAtRules((at) => { if (at.nodes && at.nodes.length === 0) at.remove(); });
  writeFileSync(target, ast.toString());
  console.log('removed.');
}
