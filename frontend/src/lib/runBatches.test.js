import { describe, expect, it } from 'vitest';
import {
  allClientsNote, confirmationOk, emptySelection, failureGroups, isFinished, isSelected, newIdempotencyKey, pageState,
  parseYears, previewLines, progressPct, refreshOnceNote, remedyFor, scopeFor, scopeSummary, selectionCount, serverFilter,
  setPage, startBody, toggleId,
} from './runBatches.js';

describe('selection', () => {
  it('toggles single rows and counts them', () => {
    let sel = emptySelection();
    sel = toggleId(sel, 7);
    sel = toggleId(sel, 9);
    expect(selectionCount(sel)).toBe(2);
    expect(isSelected(sel, 7)).toBe(true);
    sel = toggleId(sel, 7);
    expect(sel.ids).toEqual([9]);
  });

  it('selects and clears a whole page, and says whether a page is all, some or none', () => {
    const page = [1, 2, 3];
    let sel = toggleId(emptySelection(), 2);
    expect(pageState(sel, page)).toBe('some');
    sel = setPage(sel, page, true);
    expect(pageState(sel, page)).toBe('all');
    expect(sel.ids.sort()).toEqual([1, 2, 3]);
    sel = setPage(sel, page, false);
    expect(pageState(sel, page)).toBe('none');
    expect(selectionCount(sel)).toBe(0);
  });

  it('"all matching" is a server group, and picking a row after it narrows to explicit ids', () => {
    const sel = { ids: [], matching: { count: 240, filter: { band: 'exposed' } } };
    expect(selectionCount(sel)).toBe(240);
    expect(isSelected(sel, 5)).toBe(true);
    expect(pageState(sel, [1, 2])).toBe('all');
    const narrowed = toggleId(sel, 5);
    expect(narrowed).toEqual({ ids: [5], matching: null });
  });
});

describe('the server filter', () => {
  it('translates one band, state or program and nothing else', () => {
    expect(serverFilter({ band: 'exposed', state: 'GA' })).toEqual({ ok: true, filter: { band: 'exposed', state: 'GA' } });
    expect(serverFilter({})).toEqual({ ok: true, filter: {} });
  });

  it('refuses what has no server equivalent rather than approximating it', () => {
    const multi = serverFilter({ band: 'exposed|settled' });
    expect(multi.ok).toBe(false);
    expect(multi.reason).toMatch(/band filter cannot be handed to the server/);
    expect(serverFilter({ client: '~acme' }).ok).toBe(false);
    expect(serverFilter({ identified: '>=1000' }).ok).toBe(false);
  });

  it('maps a selection to the API scope', () => {
    expect(scopeFor({ ids: [4], matching: null })).toEqual({ kind: 'one', client_ids: [4] });
    expect(scopeFor({ ids: [4, 5], matching: null })).toEqual({ kind: 'list', client_ids: [4, 5] });
    expect(scopeFor({ ids: [], matching: { count: 3, filter: { state: 'GA' } } })).toEqual({ kind: 'filter', filter: { state: 'GA' } });
    expect(scopeFor({ ids: [], matching: { count: 9, filter: {} } })).toEqual({ kind: 'all' });
  });
});

describe('the request', () => {
  it('builds the typed body and omits what was not chosen', () => {
    const body = startBody({ selection: { ids: [1, 2], matching: null }, idempotencyKey: 'k', dryRun: true });
    expect(body).toEqual({
      kind: 'calculate', scope: { kind: 'list', client_ids: [1, 2] }, tax_years: [], force: false, skip_unchanged: false,
      refresh_once: true, idempotency_key: 'k', dry_run: true,
    });
    const full = startBody({
      selection: { ids: [1], matching: null }, kind: 'assess', programCode: 'GA_JTC', taxYears: [2024], force: true,
      refreshOnce: false, confirmItems: 30,
    });
    expect(full).toMatchObject({ program_code: 'GA_JTC', tax_years: [2024], force: true, refresh_once: false, confirm_items: 30 });
  });

  it('gives each opened dialog its own key', () => {
    expect(newIdempotencyKey()).not.toBe(newIdempotencyKey());
  });

  it('parses a list of years and drops what is not a year', () => {
    expect(parseYears('2024, 2025 abc 20.5')).toEqual([2024, 2025]);
    expect(parseYears('')).toEqual([]);
  });
});

describe('the preview in words', () => {
  const base = { clients: 3, items: 3, years: 'latest runnable year per client', never_run: 1, force: false,
    skip_unchanged: true, skip_coverage: 'all_years', skip_candidates_upper_bound: 2, manifests_read_for: 3 };

  it('states skips as an upper bound decided when each run starts, never a promise', () => {
    const text = previewLines(base).join(' ');
    expect(text).toMatch(/Up to 2 may be skipped as unchanged/);
    expect(text).toMatch(/upper bound/);
    expect(text).toMatch(/decided when each run starts/);
    expect(text).not.toMatch(/will be skipped/);
  });

  it('gives no bound when it did not read every client, and says so', () => {
    const text = previewLines({ ...base, skip_candidates_upper_bound: null, manifests_read_for: 200 }).join(' ');
    expect(text).toMatch(/first 200 clients only/);
    expect(text).not.toMatch(/Up to/);
  });

  it('says every client will run when forced', () => {
    expect(previewLines({ ...base, force: true }).join(' ')).toMatch(/every client will run/);
  });

  it('says nothing is skipped by default, and when earlier runs cannot support a skip yet', () => {
    expect(previewLines({ ...base, skip_unchanged: false, skip_candidates_upper_bound: 0 }).join(' ')).toMatch(/Nothing is skipped/);
    const text = previewLines({ ...base, skip_coverage: 'cannot_tell_yet', skip_candidates_upper_bound: 0 }).join(' ');
    expect(text).toMatch(/nothing can be skipped this time/);
    expect(text).not.toMatch(/Up to/);
  });

  it('names the programs when a client runs for more than one', () => {
    const text = previewLines({ ...base, programs: { GA_JTC: 2, ZZ_DEMO_JTC: 1 }, multi_program_clients: 1 }).join(' ');
    expect(text).toMatch(/Programs: GA_JTC \(2\), ZZ_DEMO_JTC \(1\)\. 1 client is run for more than one program/);
  });

  it('names the years when they were chosen', () => {
    expect(previewLines({ ...base, years: [2024, 2025] }).join(' ')).toMatch(/TY2024, TY2025/);
  });

  it('explains refresh-once both ways and flags an all-clients scope', () => {
    expect(refreshOnceNote(true)).toMatch(/each client runs once/);
    expect(refreshOnceNote(false)).toMatch(/multiplied/);
    expect(allClientsNote({ kind: 'all' })).toMatch(/every client in the book/);
    expect(allClientsNote({ kind: 'list' })).toBeNull();
  });
});

describe('typed confirmation', () => {
  it('is required only above the threshold and must equal the item count', () => {
    expect(confirmationOk({ requires_confirmation: false, items: 5 }, '')).toBe(true);
    expect(confirmationOk({ requires_confirmation: true, items: 40 }, '40')).toBe(true);
    expect(confirmationOk({ requires_confirmation: true, items: 40 }, ' 40 ')).toBe(true);
    expect(confirmationOk({ requires_confirmation: true, items: 40 }, '4')).toBe(false);
    expect(confirmationOk({ requires_confirmation: true, items: 40 }, '')).toBe(false);
  });
});

describe('progress and failures', () => {
  it('reads progress and finished state from the batch', () => {
    expect(progressPct({ progress: { done: 3, total: 4 } })).toBe(75);
    expect(progressPct({ progress: { done: 0, total: 0 } })).toBe(0);
    expect(isFinished({ status: 'partial' })).toBe(true);
    expect(isFinished({ status: 'running' })).toBe(false);
  });

  it('groups failures by dependency with a remedy, largest first', () => {
    const items = [
      { item_id: 'a', status: 'failed', error_dependency: 'validation' },
      { item_id: 'b', status: 'failed', error_dependency: 'operational_store' },
      { item_id: 'c', status: 'failed', error_dependency: 'operational_store' },
      { item_id: 'd', status: 'succeeded' },
    ];
    const groups = failureGroups(items);
    expect(groups.map((g) => [g.dependency, g.items.length])).toEqual([['operational_store', 2], ['validation', 1]]);
    expect(groups[0].remedy).toMatch(/unreachable/);
    expect(remedyFor('lookup:pay_code_category')).toMatch(/pay code category/);
    expect(remedyFor(null)).toBeNull();
  });

  it('describes the scope of a batch', () => {
    expect(scopeSummary({ scope_kind: 'all', scope_spec: { client_count: 12 } })).toBe('All clients (12)');
    expect(scopeSummary({ scope_kind: 'filter', scope_spec: { client_count: 4, filter: { band: 'exposed' } } })).toBe('4 matching band: exposed');
    expect(scopeSummary({ scope_kind: 'one', scope_spec: { client_count: 1 } })).toBe('1 selected client');
  });
});
