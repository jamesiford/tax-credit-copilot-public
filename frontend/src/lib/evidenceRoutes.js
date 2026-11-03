/**
 * Where each chat capability's answer lives on the page.
 *
 * The `plan` event names capabilities from the backend's `CAPABILITIES`. When
 * the platform emits no evidence, the pane offers a "Show on page" chip per
 * capability instead: a link to the existing view that holds the same answer,
 * for the CURRENT scope. Nothing here computes a figure; it only knows where to
 * point.
 *
 * `label` is the plain-language name used in the plan strip ("Using: ...").
 * Keep the keys in step with `CAPABILITIES` in backend/api/chat.py; an id this
 * file does not know is shown by its raw name and offered no link, never
 * guessed at.
 */
import { stepHref } from './clientFlow.js';

export const CATALOG = {
  book: { label: 'The book', needsClient: false },
  situation: { label: 'Position', needsClient: true, step: 'claimed' },
  eligibility: { label: 'Eligibility', needsClient: true, step: 'eligibility' },
  at_risk: { label: 'At risk', needsClient: true, step: 'progress' },
  trend: { label: 'Trend', needsClient: true, step: 'location' },
  multi_state: { label: 'Programs', needsClient: false, path: '/rules' },
  discovery: { label: 'Programs', needsClient: false, path: '/rules' },
  simulate: { label: 'What-if', needsClient: true, step: 'whatif' },
  explain: { label: 'Audit trail', needsClient: true, step: 'evidence' },
};

export function capabilityLabel(id) {
  return CATALOG[id]?.label ?? String(id).replace(/_/g, ' ');
}

/** "Eligibility · Trend": distinct labels in plan order. */
export function planLabels(intents = []) {
  const seen = [];
  for (const id of intents) {
    const label = capabilityLabel(id);
    if (!seen.includes(label)) seen.push(label);
  }
  return seen;
}

/**
 * One chip per distinct destination in the plan. A destination that needs a
 * client and has none is returned disabled WITH its reason, never hidden: a
 * missing chip says "this does not exist", a disabled one says "not yet".
 */
export function showOnPage(intents = [], { clientId = null, year = null, method = null } = {}) {
  const hasClient = clientId != null && clientId !== 'portfolio';
  const chips = [];
  for (const id of intents) {
    const entry = CATALOG[id];
    if (!entry) continue;
    if (chips.some((chip) => chip.label === entry.label)) continue;

    if (entry.needsClient && !hasClient) {
      chips.push({ id, label: entry.label, href: null, reason: 'Pick a client first' });
      continue;
    }
    let href;
    if (entry.step) {
      const search = new URLSearchParams();
      if (year != null) search.set('year', String(year));
      if (method) search.set('method', String(method));
      href = stepHref(entry.step, { clientId, year, search: search.toString() });
    } else {
      href = entry.path || '/';
    }
    chips.push({ id, label: entry.label, href, reason: null });
  }
  return chips;
}
