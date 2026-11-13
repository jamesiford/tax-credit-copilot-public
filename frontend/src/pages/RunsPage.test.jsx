/**
 * The Runs page: the list, one batch in detail, cancel, retry, failures by cause, polling, and the degraded states.
 *
 * Polling is exercised with the real hook and fake timers, so "stops when finished" and "pauses when the tab is
 * hidden" are the behaviour a person gets, not a stub of it.
 */
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import RunsPage from './RunsPage.jsx';

vi.mock('../api.js', async () => {
  const actual = await vi.importActual('../api.js');
  return {
    ...actual, listRunBatches: vi.fn(), fetchRunBatch: vi.fn(), fetchRunBatchItems: vi.fn(),
    cancelRunBatch: vi.fn(), retryFailedRunBatch: vi.fn(),
  };
});

const api = await import('../api.js');

const batch = (over = {}) => ({
  batch_id: 'b1', kind: 'calculate', scope_kind: 'list', scope_spec: { client_count: 4 }, status: 'running',
  cancel_requested: false, refresh_once: true, requested_by: 'pat', requested_at: '2026-03-01T09:00:00Z',
  counts: { total: 4, queued: 2, running: 1, succeeded: 1, skipped: 0, failed: 0, cancelled: 0 },
  progress: { done: 1, total: 4 }, degraded: [], ...over,
});

const item = (over = {}) => ({
  item_id: 'i1', batch_id: 'b1', seq: 0, client_id: 1001, tax_year: 2025, status: 'succeeded', attempts: 1,
  skip_reason: null, error_dependency: null, error_message: null, started_at: '2026-03-01T09:00:00Z',
  finished_at: '2026-03-01T09:00:12Z', ...over,
});

beforeEach(() => { vi.useFakeTimers({ shouldAdvanceTime: true }); });
afterEach(() => { vi.useRealTimers(); vi.clearAllMocks(); });

const settle = async (ms = 0) => { await act(async () => { await vi.advanceTimersByTimeAsync(ms); }); };

describe('the list of batches', () => {
  it('lists batches with status, scope, progress and who started them, and opens one', async () => {
    api.listRunBatches.mockResolvedValue({
      items: [batch(), batch({ batch_id: 'b2', status: 'succeeded', counts: { total: 2, queued: 0, running: 0, succeeded: 2, skipped: 0, failed: 0, cancelled: 0 }, progress: { done: 2, total: 2 } })],
      total: 2,
    });
    const onOpenBatch = vi.fn();
    render(<RunsPage onOpenBatch={onOpenBatch} />);
    await settle();
    const table = await screen.findByRole('table', { name: 'Run batches' });
    expect(within(table).getByText('Running')).toBeInTheDocument();
    expect(within(table).getByText('Succeeded')).toBeInTheDocument();
    expect(within(table).getAllByText('pat')).toHaveLength(2);
    await userEvent.setup({ advanceTimers: vi.advanceTimersByTime }).click(within(table).getAllByRole('button')[0]);
    expect(onOpenBatch).toHaveBeenCalledWith('b1');
  });

  it('treats a list response with no items as nothing run, never a crash', async () => {
    api.listRunBatches.mockResolvedValue({});
    render(<RunsPage />);
    await settle();
    expect(await screen.findByText('Nothing has been run yet')).toBeInTheDocument();
  });

  it('says what to do when nothing has been run, and that an outage is not an empty list', async () => {
    api.listRunBatches.mockResolvedValueOnce({ items: [], total: 0 });
    const { unmount } = render(<RunsPage />);
    await settle();
    expect(await screen.findByText('Nothing has been run yet')).toBeInTheDocument();
    unmount();
    api.listRunBatches.mockRejectedValue(new Error('v2 503'));
    render(<RunsPage />);
    await settle();
    expect(await screen.findByText('Runs are unavailable')).toBeInTheDocument();
    expect(screen.queryByText('Nothing has been run yet')).not.toBeInTheDocument();
    expect(screen.getByText(/Nothing was changed/)).toBeInTheDocument();
  });
});

describe('one batch', () => {
  function detail({ finishes = true } = {}) {
    const states = [
      batch(),
      batch({ status: 'succeeded', counts: { total: 4, queued: 0, running: 0, succeeded: 4, skipped: 0, failed: 0, cancelled: 0 }, progress: { done: 4, total: 4 } }),
    ];
    let n = 0;
    api.fetchRunBatch.mockImplementation(async () => states[Math.min(n++, finishes ? 1 : 0)]);
    api.fetchRunBatchItems.mockResolvedValue({ items: [item(), item({ item_id: 'i2', client_id: 1002, status: 'skipped_unchanged', skip_reason: 'identical to the last run' })], total: 2 });
  }

  it('shows progress and counts, polls while running and stops when it finishes', async () => {
    detail();
    render(<RunsPage batchId="b1" />);
    await settle();
    expect(await screen.findByRole('progressbar', { name: /1 of 4 finished/ })).toBeInTheDocument();
    expect(screen.getByText('1 of 4 finished')).toBeInTheDocument();
    await settle(1500);
    expect(await screen.findByText('4 of 4 finished')).toBeInTheDocument();
    const calls = api.fetchRunBatch.mock.calls.length;
    await settle(30000);
    expect(api.fetchRunBatch.mock.calls.length).toBe(calls);
  });

  it('shows items with the skip reason and the duration, and a link to the client', async () => {
    detail();
    const onOpenClient = vi.fn();
    render(<RunsPage batchId="b1" onOpenClient={onOpenClient} />);
    await settle();
    const table = await screen.findByRole('table', { name: 'Batch items' });
    expect(within(table).getByText('Skipped: unchanged')).toBeInTheDocument();
    expect(within(table).getByText('identical to the last run')).toBeInTheDocument();
    expect(within(table).getAllByText('12')).toHaveLength(2);
    await userEvent.setup({ advanceTimers: vi.advanceTimersByTime }).click(within(table).getByRole('button', { name: 'Account 1002' }));
    expect(onOpenClient).toHaveBeenCalledWith(1002);
  });

  it('says the batch is unavailable when the answer holds no batch (the states sweep found a crash on {})', async () => {
    api.fetchRunBatch.mockResolvedValue({});
    api.fetchRunBatchItems.mockResolvedValue({ items: [], total: 0 });
    render(<RunsPage batchId="b1" />);
    await settle();
    expect(await screen.findByText('This batch is unavailable')).toBeInTheDocument();
  });

  it('points no tab at a panel that does not exist (the sweep found aria-controls on an empty id)', async () => {
    detail();
    const { container } = render(<RunsPage batchId="b1" />);
    await settle();
    await screen.findByRole('table', { name: 'Batch items' });
    for (const tab of screen.getAllByRole('tab')) {
      const target = tab.getAttribute('aria-controls');
      if (target) expect(container.ownerDocument.getElementById(target)).not.toBeNull();
    }
  });

  it('cancels a running batch and shows that it is cancelling', async () => {
    detail({ finishes: false });
    api.cancelRunBatch.mockResolvedValue(batch({ cancel_requested: true }));
    render(<RunsPage batchId="b1" />);
    await settle();
    const cancel = await screen.findByRole('button', { name: 'Cancel' });
    await userEvent.setup({ advanceTimers: vi.advanceTimersByTime }).click(cancel);
    await settle();
    expect(api.cancelRunBatch).toHaveBeenCalledWith('b1');
  });

  it('groups failures by cause with the remedy and retries only the failed items', async () => {
    const failedBatch = batch({
      status: 'partial', counts: { total: 4, queued: 0, running: 0, succeeded: 2, skipped: 0, failed: 2, cancelled: 0 }, progress: { done: 4, total: 4 },
    });
    api.fetchRunBatch.mockResolvedValue(failedBatch);
    const failed = [
      item({ item_id: 'f1', client_id: 3, status: 'failed', error_dependency: 'operational_store', error_message: 'the server could not be reached.' }),
      item({ item_id: 'f2', client_id: 4, status: 'failed', error_dependency: 'operational_store', error_message: 'the server could not be reached.' }),
    ];
    api.fetchRunBatchItems.mockImplementation(async (id, opts) => ({ items: opts?.status === 'failed' ? failed : failed.concat(item()), total: 3 }));
    api.retryFailedRunBatch.mockResolvedValue({ ...failedBatch, requeued: 2 });
    render(<RunsPage batchId="b1" />);
    await settle();
    expect(await screen.findByText('2 failed: operational_store')).toBeInTheDocument();
    expect(screen.getByText(/The store was unreachable\. Check the connection, then retry the failed items\./)).toBeInTheDocument();
    await userEvent.setup({ advanceTimers: vi.advanceTimersByTime }).click(screen.getByRole('button', { name: 'Retry failed (2)' }));
    await settle();
    expect(api.retryFailedRunBatch).toHaveBeenCalledWith('b1');
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
  });

  it('shows the degraded worker banner and never "not assessed" for a store that cannot answer', async () => {
    api.fetchRunBatch.mockResolvedValue(batch({
      status: 'queued', counts: { total: 2, queued: 2, running: 0, succeeded: 0, skipped: 0, failed: 0, cancelled: 0 }, progress: { done: 0, total: 2 },
      degraded: [{ dependency: 'run_worker', impact: 'queued runs are not progressing', remedy: 'Start the worker.' }],
    }));
    api.fetchRunBatchItems.mockResolvedValue({ items: [], total: 0 });
    render(<RunsPage batchId="b1" />);
    await settle();
    expect(await screen.findByText('Part of this page is unavailable')).toBeInTheDocument();
    expect(screen.getByText('run_worker')).toBeInTheDocument();
    expect(screen.getByText('Start the worker.')).toBeInTheDocument();
  });

  it('keeps the last numbers and says updates are delayed when a poll fails', async () => {
    api.fetchRunBatch.mockResolvedValueOnce(batch()).mockRejectedValue(new Error('v2 503'));
    api.fetchRunBatchItems.mockResolvedValue({ items: [item()], total: 1 });
    render(<RunsPage batchId="b1" />);
    await settle();
    await screen.findByText('1 of 4 finished');
    await settle(1600);
    expect(await screen.findByText('Updates are delayed')).toBeInTheDocument();
    expect(screen.getByText('1 of 4 finished')).toBeInTheDocument();
  });

  it('says the batch is unavailable (not empty) when it cannot be read at all', async () => {
    api.fetchRunBatch.mockRejectedValue(new Error('Unknown run batch zz.'));
    render(<RunsPage batchId="zz" />);
    await settle();
    expect(await screen.findByText('This batch is unavailable')).toBeInTheDocument();
    expect(screen.getByText(/Unknown run batch zz\./)).toBeInTheDocument();
  });

  it('pauses while the tab is hidden', async () => {
    detail({ finishes: false });
    render(<RunsPage batchId="b1" />);
    await settle();
    await screen.findByText('1 of 4 finished');
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' });
    document.dispatchEvent(new Event('visibilitychange'));
    await settle(2000);
    const frozen = api.fetchRunBatch.mock.calls.length;
    await settle(30000);
    expect(api.fetchRunBatch.mock.calls.length).toBe(frozen);
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'visible' });
    document.dispatchEvent(new Event('visibilitychange'));
    await settle();
    expect(api.fetchRunBatch.mock.calls.length).toBeGreaterThan(frozen);
  });
});
