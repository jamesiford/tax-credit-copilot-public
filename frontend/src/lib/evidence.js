/**
 * The Ask workspace's evidence contract. Framework-free.
 *
 * The model narrates; the numbers come from the engine. So the right-hand pane
 * of the Ask workspace never shows model prose: it shows EVIDENCE ITEMS the
 * platform rendered, shaped like the platform's tool-result envelope:
 *
 *   { tool, kind?, title?, facts?, blocks: [{ kind, ... }], provenance?,
 *     disclaimer?, confirmation? }
 *
 * This module validates an item and hands back a normalised copy. It never
 * computes, rounds, re-formats or re-orders a figure: every value is the string
 * the platform wrote (a JSON number is rendered as its own digits and no more).
 * An item or block that does not fit the contract is DROPPED and counted, never
 * repaired: a repaired figure is a figure nobody produced.
 *
 * Documented for the backend in docs/design/ASK-EVIDENCE-CONTRACT.md.
 */

export const BLOCK_KINDS = ['text', 'kpis', 'table', 'callout', 'list'];
export const ITEM_KINDS = ['evidence', 'confirmation'];

//: A tone is a --state-* family and nothing else. Anything else is neutral, so
//: a platform cannot paint a block in the selection blue or a free colour.
export const TONES = ['neutral', 'above-min', 'below-min', 'partial', 'base-year'];

const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const isScalar = (value) => typeof value === 'string' || (typeof value === 'number' && Number.isFinite(value));
const text = (value) => String(value);
const tone = (value) => (TONES.includes(value) ? value : 'neutral');

function cleanFacts(facts) {
  if (!isObject(facts)) return {};
  return Object.fromEntries(
    Object.entries(facts).filter(([, value]) => isScalar(value)).map(([key, value]) => [key, text(value)]),
  );
}

function cleanBlock(block) {
  if (!isObject(block) || !BLOCK_KINDS.includes(block.kind)) return null;
  const title = isScalar(block.title) ? text(block.title) : null;

  switch (block.kind) {
    case 'text':
      return isScalar(block.text) ? { kind: 'text', title, text: text(block.text) } : null;
    case 'callout':
      return isScalar(block.text)
        ? { kind: 'callout', title, text: text(block.text), tone: tone(block.tone) }
        : null;
    case 'list': {
      if (!Array.isArray(block.rows)) return null;
      const rows = block.rows.filter(isScalar).map(text);
      return rows.length ? { kind: 'list', title, rows } : null;
    }
    case 'kpis': {
      if (!Array.isArray(block.rows)) return null;
      const rows = block.rows
        .filter((row) => isObject(row) && isScalar(row.label) && isScalar(row.value))
        .map((row) => ({
          label: text(row.label),
          value: text(row.value),
          sub: isScalar(row.sub) ? text(row.sub) : null,
          tone: tone(row.tone),
        }));
      return rows.length ? { kind: 'kpis', title, rows } : null;
    }
    case 'table': {
      if (!Array.isArray(block.columns) || !Array.isArray(block.rows)) return null;
      const columns = block.columns.filter(isScalar).map(text);
      if (!columns.length) return null;
      // A row of the wrong width is dropped, not padded: a padded cell is a
      // figure that was never in the platform's answer.
      const rows = block.rows
        .filter((row) => Array.isArray(row) && row.length === columns.length && row.every(isScalar))
        .map((row) => row.map(text));
      return {
        kind: 'table', title, columns, rows,
        align: Array.isArray(block.align) ? block.align.map((a) => (a === 'right' ? 'right' : 'left')) : null,
      };
    }
    default:
      return null;
  }
}

function cleanProvenance(provenance) {
  if (!isObject(provenance)) return null;
  const out = {};
  for (const key of ['run_id', 'rule_pack', 'trail_hash', 'produced_at']) {
    if (isScalar(provenance[key])) out[key] = text(provenance[key]);
  }
  return Object.keys(out).length ? out : null;
}

function cleanConfirmation(confirmation) {
  if (!isObject(confirmation)) return null;
  const blocks = (Array.isArray(confirmation.blocks) ? confirmation.blocks : []).map(cleanBlock).filter(Boolean);
  return {
    token: isScalar(confirmation.token) ? text(confirmation.token) : null,
    summary: isScalar(confirmation.summary) ? text(confirmation.summary) : null,
    blocks,
    expires_at: isScalar(confirmation.expires_at) ? text(confirmation.expires_at) : null,
    confirm_label: isScalar(confirmation.confirm_label) ? text(confirmation.confirm_label) : 'Confirm',
    cancel_label: isScalar(confirmation.cancel_label) ? text(confirmation.cancel_label) : 'Cancel',
  };
}

/**
 * Validate one evidence item. Returns `{ ok: true, item, dropped }` or
 * `{ ok: false, reason }`. `dropped` counts blocks that did not fit the
 * contract; the pane says so rather than quietly showing less.
 */
export function validateEvidence(raw) {
  if (!isObject(raw)) return { ok: false, reason: 'not an object' };
  if (!isScalar(raw.tool) || text(raw.tool).trim() === '') return { ok: false, reason: 'no tool' };

  const kind = raw.kind === undefined ? 'evidence' : raw.kind;
  if (!ITEM_KINDS.includes(kind)) return { ok: false, reason: `unknown kind ${text(kind)}` };

  const rawBlocks = Array.isArray(raw.blocks) ? raw.blocks : [];
  const blocks = rawBlocks.map(cleanBlock).filter(Boolean);
  const confirmation = kind === 'confirmation' ? cleanConfirmation(raw.confirmation) : null;

  if (kind === 'confirmation' && !confirmation) return { ok: false, reason: 'confirmation without a payload' };
  if (kind === 'evidence' && !blocks.length) return { ok: false, reason: 'no renderable blocks' };

  return {
    ok: true,
    dropped: rawBlocks.length - blocks.length,
    item: {
      id: isScalar(raw.id) ? text(raw.id) : null,
      tool: text(raw.tool),
      kind,
      title: isScalar(raw.title) ? text(raw.title) : null,
      facts: cleanFacts(raw.facts),
      blocks,
      provenance: cleanProvenance(raw.provenance),
      disclaimer: isScalar(raw.disclaimer) ? text(raw.disclaimer) : null,
      confirmation,
    },
  };
}

/** The first table's row count: what a tab's count chip says it holds. */
export function tabCount(item) {
  const table = item.blocks.find((b) => b.kind === 'table');
  return table ? table.rows.length : null;
}

/** A stable key for an item: the platform's id, else its tool and position. */
export function itemKey(item, index) {
  return item.id || `${item.tool}-${index}`;
}

/**
 * Tabs for the pane: one per item, in the order the platform sent them. A
 * confirmation is a tab too (it is evidence of what would be written).
 */
export function evidenceTabs(items) {
  return items.map((item, index) => ({
    id: itemKey(item, index),
    label: item.title || item.tool,
    count: tabCount(item),
  }));
}

/** Add an item, replacing one with the same id (a re-sent item supersedes). */
export function addEvidence(items, item) {
  if (item.id) {
    const at = items.findIndex((existing) => existing.id === item.id);
    if (at >= 0) return items.map((existing, i) => (i === at ? item : existing));
  }
  return [...items, item];
}

/** Whether a confirmation has expired at `now` (ms). No expiry never expires. */
export function isExpired(confirmation, now = Date.now()) {
  if (!confirmation?.expires_at) return false;
  const at = Date.parse(confirmation.expires_at);
  return Number.isFinite(at) && at <= now;
}
