import { useInRouterContext, useNavigate } from 'react-router-dom';
import { startRunBatch } from '../api.js';
import { newIdempotencyKey } from './runBatches.js';

/**
 * "Run as a tracked batch" for the single-client controls. OFF by default.
 *
 * Run assessment, the per-row Assess link and "Run TY… now" block until the work is done. With this on they queue a
 * one-client batch instead and open its progress page, which is what a large client needs (a calculation can take
 * minutes). It is off in this release so the existing controls behave exactly as before; the recommendation is to
 * turn it on by default once the worker is deployed everywhere the portal is (docs/architecture/RUN-ORCHESTRATION.md).
 *
 * Enable with `VITE_RUN_AS_BATCH=true` at build time, or `localStorage['tcc.run-as-batch'] = '1'` to try it in one
 * browser.
 */
export const RUN_AS_BATCH_KEY = 'tcc.run-as-batch';

export function runAsBatchEnabled() {
  if (import.meta.env?.VITE_RUN_AS_BATCH === 'true') return true;
  try { return globalThis.localStorage?.getItem(RUN_AS_BATCH_KEY) === '1'; } catch { return false; }
}

/**
 * Queue a one-client batch with the same meaning the blocking control has. `force` is on because the existing
 * controls always run; skipping "unchanged" is a decision a person makes for a group, not for the one client
 * they just asked about.
 */
export function queueOneClient({ kind, clientId, year = null, programCode = null }) {
  return startRunBatch({
    kind,
    scope: { kind: 'one', client_ids: [clientId] },
    ...(programCode ? { program_code: programCode } : {}),
    tax_years: year ? [year] : [],
    force: true,
    refresh_once: true,
    idempotency_key: newIdempotencyKey(),
    dry_run: false,
  });
}

/** The navigate function when there is a router, else null (a view rendered alone in a test or a story). */
export function useBatchNavigate() {
  const inRouter = useInRouterContext();
  // `inRouter` is fixed for the life of a mount, so this conditional hook call is stable.
  // eslint-disable-next-line react-hooks/rules-of-hooks
  return inRouter ? useNavigate() : null;
}

export const batchPath = (batch) => `/runs/${encodeURIComponent(batch.batch_id)}`;
