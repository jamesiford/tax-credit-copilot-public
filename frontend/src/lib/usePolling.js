import { useEffect, useRef, useState } from 'react';

/**
 * Poll `load` until `done(result)` says stop, backing off while nothing changes and pausing while the tab is hidden.
 *
 * Returns `{ data, error, reload }`. Backoff: the delay grows by half each time the answer looks the same, up to
 * `maxMs`, and resets when it changes, so a long batch costs a request every few seconds rather than every second.
 * Hidden tabs do not poll; becoming visible reloads at once. A failed poll keeps the last good data and retries at
 * the current delay, so one dropped request does not blank a page that was working.
 */
export default function usePolling(load, { done = () => false, baseMs = 1500, maxMs = 15000, key = null } = {}) {
  const [state, setState] = useState({ data: null, error: null });
  const loadRef = useRef(load);
  const doneRef = useRef(done);
  loadRef.current = load;
  doneRef.current = done;
  const reloadRef = useRef(() => {});

  useEffect(() => {
    let cancelled = false;
    let timer = null;
    let delay = baseMs;
    let last = null;
    const hidden = () => typeof document !== 'undefined' && document.visibilityState === 'hidden';

    const schedule = () => {
      if (cancelled) return;
      timer = setTimeout(tick, delay);
    };

    async function tick() {
      timer = null;
      if (cancelled) return;
      if (hidden()) return; // resumes from the visibilitychange handler
      try {
        const data = await loadRef.current();
        if (cancelled) return;
        setState({ data, error: null });
        if (doneRef.current(data)) return;
        const fingerprint = JSON.stringify(data?.counts ?? data?.progress ?? data?.total ?? data);
        delay = fingerprint === last ? Math.min(maxMs, Math.round(delay * 1.5)) : baseMs;
        last = fingerprint;
      } catch (e) {
        if (cancelled) return;
        setState((prev) => ({ data: prev.data, error: e }));
        delay = Math.min(maxMs, Math.round(delay * 1.5));
      }
      schedule();
    }

    const onVisible = () => {
      if (!hidden() && timer == null && !cancelled) { delay = baseMs; tick(); }
    };
    reloadRef.current = () => { if (timer) clearTimeout(timer); delay = baseMs; tick(); };
    document.addEventListener('visibilitychange', onVisible);
    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [key, baseMs, maxMs]);

  return { ...state, reload: () => reloadRef.current() };
}
