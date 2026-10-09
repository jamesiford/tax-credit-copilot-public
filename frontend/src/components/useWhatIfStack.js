import { useCallback, useEffect, useState } from 'react';
import {
  addRows, readStack, removeToken, subscribe,
} from '../lib/whatIfStack.js';
import { stackPatch } from '../lib/whatIf.js';

/**
 * The What-if stack for one client-year-method, from any page (29 Sep).
 *
 * `openSearch` is the client page's query string that opens What-if on the
 * stack and runs it — the one place the stack is projected.
 */
export default function useWhatIfStack({ clientId, taxYear, method = 'min_max' }) {
  const scope = { clientId, taxYear, method };
  const [entries, setEntries] = useState(() => readStack(scope));

  useEffect(() => {
    const refresh = () => setEntries(readStack({ clientId, taxYear, method }));
    refresh();
    return subscribe(refresh);
  }, [clientId, taxYear, method]);

  const add = useCallback((rows) => addRows({ clientId, taxYear, method }, rows), [clientId, taxYear, method]);
  const remove = useCallback((token) => removeToken({ clientId, taxYear, method }, token), [clientId, taxYear, method]);

  const openSearch = new URLSearchParams(
    Object.entries(stackPatch(entries, { taxYear, method, open: true })).filter(([, v]) => v),
  ).toString();

  return {
    entries,
    tokens: new Set(entries.map((e) => e.token)),
    add,
    remove,
    openHref: `/c/${encodeURIComponent(clientId)}?${openSearch}`,
  };
}
