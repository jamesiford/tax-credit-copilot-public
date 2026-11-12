/**
 * Production frontend code names no client. A demo client written into a component walks a customer's
 * user to a page that does not exist for them. Fixtures and the scripted demo tour are named below;
 * comments and tests are free to describe a client.
 */
import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const SRC = path.resolve(__dirname, '..');
const ALLOWED = new Set([
  'lib/demoTour.js', // scripted demo, loaded only when VITE_DEMO_TOUR is set
  'lib/askFixtures.js', // dev-only fixtures behind import.meta.env.DEV
]);
const PATTERN = /\b(1001|200[1-5])\b|Candle Bottle|Cascade|Northwind|Ironbridge|Halloway/;

function files(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return files(full);
    return /\.(js|jsx)$/.test(entry.name) && !/\.test\.jsx?$/.test(entry.name) ? [full] : [];
  });
}

function codeLines(text) {
  let inBlock = false;
  return text.split('\n').map((line, index) => {
    const trimmed = line.trim();
    if (inBlock) { if (trimmed.includes('*/')) inBlock = false; return null; }
    if (trimmed.startsWith('/*')) { if (!trimmed.includes('*/')) inBlock = true; return null; }
    if (trimmed.startsWith('//') || trimmed.startsWith('*')) return null;
    return { line: line.replace(/\s\/\/.*$/, ''), number: index + 1 };
  }).filter(Boolean);
}

describe('production frontend code', () => {
  it('names no specific client', () => {
    const breaches = [];
    for (const file of files(SRC)) {
      const rel = path.relative(SRC, file).split(path.sep).join('/');
      if (ALLOWED.has(rel)) continue;
      for (const { line, number } of codeLines(fs.readFileSync(file, 'utf8'))) {
        if (PATTERN.test(line)) breaches.push(`${rel}:${number}: ${line.trim()}`);
      }
    }
    expect(breaches).toEqual([]);
  });
});
