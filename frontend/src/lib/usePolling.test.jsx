import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import usePolling from './usePolling.js';

function setHidden(hidden) {
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => (hidden ? 'hidden' : 'visible') });
  document.dispatchEvent(new Event('visibilitychange'));
}

describe('usePolling', () => {
  beforeEach(() => { vi.useFakeTimers(); setHidden(false); });
  afterEach(() => { vi.useRealTimers(); setHidden(false); });

  it('loads at once and keeps polling until done says stop', async () => {
    const load = vi.fn()
      .mockResolvedValueOnce({ counts: { queued: 2 }, status: 'queued' })
      .mockResolvedValueOnce({ counts: { queued: 1 }, status: 'running' })
      .mockResolvedValue({ counts: { queued: 0 }, status: 'succeeded' });
    const { result } = renderHook(() => usePolling(load, { done: (d) => d?.status === 'succeeded', baseMs: 100 }));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(result.current.data.status).toBe('queued');
    await act(async () => { await vi.advanceTimersByTimeAsync(100); });
    expect(result.current.data.status).toBe('running');
    await act(async () => { await vi.advanceTimersByTimeAsync(100); });
    expect(result.current.data.status).toBe('succeeded');
    const calls = load.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    expect(load.mock.calls.length).toBe(calls);
  });

  it('backs off while nothing changes and resets when something does', async () => {
    let n = 0;
    const load = vi.fn(async () => ({ counts: { queued: n < 4 ? 1 : 0 } }));
    renderHook(() => usePolling(load, { baseMs: 100, maxMs: 1000 }));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(load).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(100); });
    expect(load).toHaveBeenCalledTimes(2);
    // identical answers: the next delay is 150ms, not 100ms
    await act(async () => { await vi.advanceTimersByTimeAsync(100); });
    expect(load).toHaveBeenCalledTimes(2);
    await act(async () => { await vi.advanceTimersByTimeAsync(50); });
    expect(load).toHaveBeenCalledTimes(3);
    n = 10;
    await act(async () => { await vi.advanceTimersByTimeAsync(400); });
    const afterChange = load.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(100); });
    expect(load.mock.calls.length).toBe(afterChange + 1);
  });

  it('pauses while the tab is hidden and resumes on becoming visible', async () => {
    const load = vi.fn(async () => ({ counts: { queued: 1 } }));
    renderHook(() => usePolling(load, { baseMs: 100 }));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    act(() => setHidden(true));
    const calls = load.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
    expect(load.mock.calls.length).toBeLessThanOrEqual(calls + 1);
    const frozen = load.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
    expect(load.mock.calls.length).toBe(frozen);
    act(() => setHidden(false));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(load.mock.calls.length).toBe(frozen + 1);
  });

  it('keeps the last good data when a poll fails, and reports the error', async () => {
    const load = vi.fn()
      .mockResolvedValueOnce({ counts: { queued: 1 }, status: 'running' })
      .mockRejectedValueOnce(new Error('v2 503'))
      .mockResolvedValue({ counts: { queued: 0 }, status: 'succeeded' });
    const { result } = renderHook(() => usePolling(load, { done: (d) => d?.status === 'succeeded', baseMs: 100 }));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    await act(async () => { await vi.advanceTimersByTimeAsync(100); });
    expect(result.current.data.status).toBe('running');
    expect(result.current.error.message).toBe('v2 503');
    await act(async () => { await vi.advanceTimersByTimeAsync(300); });
    expect(result.current.data.status).toBe('succeeded');
    expect(result.current.error).toBeNull();
  });

  it('reload polls again after a finished batch is retried', async () => {
    let status = 'succeeded';
    const load = vi.fn(async () => ({ status, counts: { queued: status === 'succeeded' ? 0 : 1 } }));
    const { result } = renderHook(() => usePolling(load, { done: (d) => d?.status === 'succeeded', baseMs: 100 }));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    const calls = load.mock.calls.length;
    status = 'running';
    await act(async () => { result.current.reload(); await vi.advanceTimersByTimeAsync(0); });
    expect(load.mock.calls.length).toBe(calls + 1);
    expect(result.current.data.status).toBe('running');
  });
});
