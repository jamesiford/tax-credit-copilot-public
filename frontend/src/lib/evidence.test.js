import { describe, expect, it } from 'vitest';
import {
  addEvidence, evidenceTabs, isExpired, tabCount, validateEvidence,
} from './evidence.js';
import {
  CONFIRMATION_EVIDENCE, ELIGIBILITY_EVIDENCE, TREND_EVIDENCE,
} from './askFixtures.js';

const ok = (raw) => {
  const result = validateEvidence(raw);
  expect(result.ok).toBe(true);
  return result;
};

describe('the evidence contract', () => {
  it('accepts the platform fixtures and keeps every figure as the string it was', () => {
    const { item } = ok(ELIGIBILITY_EVIDENCE);
    const kpis = item.blocks.find((b) => b.kind === 'kpis');
    expect(kpis.rows.map((r) => r.value)).toEqual(['539', '410.13', '24']);
    const table = item.blocks.find((b) => b.kind === 'table');
    expect(table.rows[0]).toEqual(['GA_GA-001', '-4.0', 'Below minimum']);
  });

  it('never reformats a number: trailing zeros and signs survive', () => {
    const { item } = ok({
      tool: 'x',
      blocks: [{ kind: 'table', columns: ['a'], rows: [['410.10'], ['-0.50'], [3]] }],
    });
    expect(item.blocks[0].rows).toEqual([['410.10'], ['-0.50'], ['3']]);
  });

  it('rejects what is not an item, and an item with nothing to show', () => {
    expect(validateEvidence(null).ok).toBe(false);
    expect(validateEvidence([]).ok).toBe(false);
    expect(validateEvidence({ blocks: [] }).reason).toBe('no tool');
    expect(validateEvidence({ tool: 't', blocks: [] }).reason).toBe('no renderable blocks');
    expect(validateEvidence({ tool: 't', kind: 'spooky', blocks: [] }).ok).toBe(false);
  });

  it('drops a block it does not understand and says how many', () => {
    const result = ok({
      tool: 't',
      blocks: [
        { kind: 'text', text: 'kept' },
        { kind: 'hologram', text: 'dropped' },
        { kind: 'table', columns: [], rows: [] },
      ],
    });
    expect(result.item.blocks).toHaveLength(1);
    expect(result.dropped).toBe(2);
  });

  it('drops a table row of the wrong width rather than padding it', () => {
    const { item } = ok({
      tool: 't',
      blocks: [{ kind: 'table', columns: ['a', 'b'], rows: [['1', '2'], ['only one'], ['1', '2', '3']] }],
    });
    expect(item.blocks[0].rows).toEqual([['1', '2']]);
  });

  it('a tone is a --state-* family; anything else is neutral', () => {
    const { item } = ok({
      tool: 't',
      blocks: [
        { kind: 'callout', text: 'x', tone: 'brand' },
        { kind: 'callout', text: 'y', tone: 'below-min' },
      ],
    });
    expect(item.blocks.map((b) => b.tone)).toEqual(['neutral', 'below-min']);
  });

  it('keeps provenance and the disclaimer verbatim, and drops what it does not know', () => {
    const { item } = ok(ELIGIBILITY_EVIDENCE);
    expect(item.provenance).toEqual(ELIGIBILITY_EVIDENCE.provenance);
    expect(item.disclaimer).toBe(ELIGIBILITY_EVIDENCE.disclaimer);
    expect(ok({ tool: 't', blocks: [{ kind: 'text', text: 'a' }], provenance: { secret: 'x' } }).item.provenance).toBeNull();
  });

  it('a confirmation needs its payload, and carries its own blocks', () => {
    expect(validateEvidence({ tool: 't', kind: 'confirmation' }).reason).toMatch(/confirmation/);
    const { item } = ok(CONFIRMATION_EVIDENCE);
    expect(item.kind).toBe('confirmation');
    expect(item.confirmation.blocks).toHaveLength(1);
    expect(item.confirmation.confirm_label).toBe('Confirm');
  });

  it('tabs carry the row count of the list they hold, and none when there is no list', () => {
    const items = [ok(ELIGIBILITY_EVIDENCE).item, ok({ tool: 'n', blocks: [{ kind: 'text', text: 'a' }] }).item];
    expect(tabCount(items[0])).toBe(3);
    expect(tabCount(items[1])).toBeNull();
    expect(evidenceTabs(items).map((t) => [t.label, t.count])).toEqual([['Eligibility', 3], ['n', null]]);
  });

  it('a re-sent item supersedes the one with its id', () => {
    const a = ok(ELIGIBILITY_EVIDENCE).item;
    const b = ok(TREND_EVIDENCE).item;
    const again = { ...a, title: 'Eligibility (updated)' };
    const next = addEvidence(addEvidence([], a), b);
    expect(addEvidence(next, again).map((i) => i.title)).toEqual(['Eligibility (updated)', 'Trend']);
    expect(addEvidence(next, again)).toHaveLength(2);
  });

  it('expiry: none never expires, a past time has', () => {
    expect(isExpired({ expires_at: null })).toBe(false);
    expect(isExpired({ expires_at: '2000-01-01T00:00:00Z' }, Date.parse('2001-01-01T00:00:00Z'))).toBe(true);
    expect(isExpired({ expires_at: '2099-01-01T00:00:00Z' })).toBe(false);
  });
});
