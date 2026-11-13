import { useCallback, useMemo, useState } from 'react';
import { ListChecks } from 'lucide-react';
import {
  cancelRunBatch, fetchRunBatch, fetchRunBatchItems, listRunBatches, retryFailedRunBatch,
} from '../api.js';
import PageHeader from '../components/PageHeader.jsx';
import Button from '../components/ui/Button.jsx';
import Callout from '../components/ui/Callout.jsx';
import Card from '../components/ui/Card.jsx';
import DegradedBanner from '../components/ui/DegradedBanner.jsx';
import EmptyState from '../components/ui/EmptyState.jsx';
import KpiTile, { KpiRow } from '../components/ui/KpiTile.jsx';
import Pill from '../components/ui/Pill.jsx';
import Skeleton from '../components/ui/Skeleton.jsx';
import Tabs from '../components/ui/Tabs.jsx';
import usePolling from '../lib/usePolling.js';
import {
  STATUS_LABEL, STATUS_PILL, durationSeconds, failureGroups, isFinished, progressPct, scopeSummary,
} from '../lib/runBatches.js';
import '../components/runs/runs.css';

const PAGE = 25;
const when = (iso) => (iso ? iso.replace('T', ' ').slice(0, 16) : '—');

function StatusPill({ status }) {
  return <Pill variant={STATUS_PILL[status] || 'neutral'}>{STATUS_LABEL[status] || status}</Pill>;
}

/** A native progress element: accessible by default and styled by class, so no inline width is computed. */
function Progress({ batch }) {
  return (
    <progress
      className="runs-progress" max={batch.progress.total || 1} value={batch.progress.done}
      aria-label={`${batch.progress.done} of ${batch.progress.total} finished (${progressPct(batch)}%)`}
    />
  );
}

function BatchList({ onOpen }) {
  const { data, error } = usePolling(() => listRunBatches({ limit: 50 }), {
    done: (d) => (d?.items || []).every((b) => isFinished(b)), baseMs: 4000, maxMs: 20000,
  });
  if (error && !data) {
    return <EmptyState title="Runs are unavailable">{error.message}<br />Nothing was changed; reload the page to try again.</EmptyState>;
  }
  if (!data) return <Skeleton lines={5} label="Loading runs" />;
  if (!data.items.length) {
    return (
      <EmptyState title="Nothing has been run yet">
        Select clients in the portfolio and choose &ldquo;Run for N clients&rdquo;. Batches you start appear here with their progress.
      </EmptyState>
    );
  }
  return (
    <table className="tbl-compact" aria-label="Run batches">
      <thead>
        <tr><th>Started</th><th>What</th><th>Scope</th><th>Status</th><th className="num">Done</th><th className="num">Failed</th><th>By</th></tr>
      </thead>
      <tbody>
        {data.items.map((b) => (
          <tr key={b.batch_id}>
            <td>
              <button type="button" className="runs-row-link" onClick={() => onOpen(b.batch_id)} aria-label={`Open batch started ${when(b.requested_at)}`}>
                {when(b.requested_at)}
              </button>
            </td>
            <td>{b.kind.replace(/_/g, ' ')}</td>
            <td>{scopeSummary(b)}</td>
            <td><StatusPill status={b.status} /></td>
            <td className="num">{b.progress.done} / {b.progress.total}</td>
            <td className="num">{b.counts.failed || '—'}</td>
            <td className="small">{b.requested_by}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Failures({ items }) {
  const groups = failureGroups(items);
  if (!groups.length) return null;
  return (
    <Card title="Failures" subtitle="Grouped by what caused them">
      <div className="runs-failures">
        {groups.map((g) => (
          <Callout key={g.dependency} tone="below-min" title={`${g.items.length} failed: ${g.dependency}`}>
            <p>{g.remedy}</p>
            <ul className="small">
              {g.items.slice(0, 5).map((i) => <li key={i.item_id}>Account {i.client_id}{i.tax_year ? `, TY${i.tax_year}` : ''}: {i.error_message}</li>)}
              {g.items.length > 5 ? <li>and {g.items.length - 5} more</li> : null}
            </ul>
          </Callout>
        ))}
      </div>
    </Card>
  );
}

function ItemsTable({ page, onOpenClient }) {
  if (!page) return <Skeleton lines={4} label="Loading items" />;
  if (!page.items.length) return <EmptyState title="No items match">Nothing has this status in the batch.</EmptyState>;
  return (
    <table className="tbl-compact" aria-label="Batch items">
      <thead><tr><th>Client</th><th>Year</th><th>Status</th><th>Detail</th><th className="num">Tries</th><th className="num">Seconds</th></tr></thead>
      <tbody>
        {page.items.map((i) => (
          <tr key={i.item_id}>
            <td>
              <button type="button" className="runs-row-link" onClick={() => onOpenClient?.(i.client_id)}>Account {i.client_id}</button>
            </td>
            <td>{i.tax_year ? `TY${i.tax_year}` : 'latest'}</td>
            <td><StatusPill status={i.status} /></td>
            <td className="small">{i.skip_reason || i.error_message || ''}</td>
            <td className="num">{i.attempts}</td>
            <td className="num">{durationSeconds(i) ?? '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function BatchActions({ batch, busy, onCancel, onRetry }) {
  const active = !isFinished(batch);
  return (
    <>
      <Button variant="danger" size="sm" disabled={!active || busy || batch.cancel_requested} onClick={onCancel}>
        {batch.cancel_requested && active ? 'Cancelling…' : 'Cancel'}
      </Button>
      <Button size="sm" disabled={!batch.counts.failed || busy} onClick={onRetry}>
        Retry failed{batch.counts.failed ? ` (${batch.counts.failed})` : ''}
      </Button>
    </>
  );
}

function Detail({ batchId, onOpenClient }) {
  const [filter, setFilter] = useState('');
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(null);

  const load = useCallback(async () => {
    const batch = await fetchRunBatch(batchId);
    const [page, failed] = await Promise.all([
      fetchRunBatchItems(batchId, { status: filter || undefined, limit: PAGE, offset }),
      batch.counts.failed ? fetchRunBatchItems(batchId, { status: 'failed', limit: 200 }) : Promise.resolve({ items: [] }),
    ]);
    return { ...batch, page, failed: failed.items };
  }, [batchId, filter, offset]);

  const { data, error, reload } = usePolling(load, { done: isFinished, key: `${batchId}:${filter}:${offset}` });

  const act = async (fn) => {
    setBusy(true);
    setActionError(null);
    try { await fn(batchId); reload(); } catch (e) { setActionError(e); } finally { setBusy(false); }
  };

  const tabs = useMemo(() => (data ? [
    { id: '', label: `All (${data.counts.total})` },
    { id: 'failed', label: `Failed (${data.counts.failed})` },
    { id: 'skipped_unchanged', label: 'Skipped: unchanged' },
    { id: 'succeeded', label: `Succeeded (${data.counts.succeeded})` },
    { id: 'queued', label: `Queued (${data.counts.queued})` },
  ] : []), [data]);

  if (error && !data) return <EmptyState title="This batch is unavailable">{error.message}<br />Nothing was changed.</EmptyState>;
  if (!data) return <Skeleton lines={6} label="Loading the batch" />;

  const total = data.page.total;
  return (
    <>
      <DegradedBanner degraded={data.degraded} />
      {error ? <Callout tone="partial" title="Updates are delayed">{error.message}. The numbers below are the last ones received.</Callout> : null}
      {actionError ? <Callout tone="below-min" title="That did not work">{actionError.message}</Callout> : null}
      <Card
        title={`${data.kind.replace(/_/g, ' ')} · ${scopeSummary(data)}`}
        subtitle={`Started ${when(data.requested_at)} by ${data.requested_by}`}
        actions={<BatchActions batch={data} busy={busy} onCancel={() => act(cancelRunBatch)} onRetry={() => act(retryFailedRunBatch)} />}
      >
        <div className="runs-detail-head">
          <StatusPill status={data.status} />
          <span className="small">{data.progress.done} of {data.progress.total} finished</span>
        </div>
        <Progress batch={data} />
        <KpiRow label="Items by outcome">
          <KpiTile label="Queued" value={String(data.counts.queued)} />
          <KpiTile label="Running" value={String(data.counts.running)} tone={data.counts.running ? 'partial' : 'neutral'} />
          <KpiTile label="Succeeded" value={String(data.counts.succeeded)} tone={data.counts.succeeded ? 'above-min' : 'neutral'} />
          <KpiTile label="Skipped" value={String(data.counts.skipped)} sub="unchanged or no data" />
          <KpiTile label="Failed" value={String(data.counts.failed)} tone={data.counts.failed ? 'below-min' : 'neutral'} />
          <KpiTile label="Cancelled" value={String(data.counts.cancelled)} />
        </KpiRow>
        {data.refresh_once ? null : <p className="small muted">One run per client and year: each run refreshes every year.</p>}
      </Card>

      <Failures items={data.failed} />

      <Card flush title="Items" tabs={<Tabs label="Item status" idPrefix="runs-items" variant="segmented" tabs={tabs} active={filter} onChange={(id) => { setFilter(id); setOffset(0); }} />}>
        <ItemsTable page={data.page} onOpenClient={onOpenClient} />
        <div className="runs-detail-head" role="navigation" aria-label="Item pages">
          <Button size="sm" variant="ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</Button>
          <span className="small muted">{total ? `${offset + 1}–${Math.min(total, offset + PAGE)} of ${total}` : '0 items'}</span>
          <Button size="sm" variant="ghost" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>Next</Button>
        </div>
      </Card>
    </>
  );
}

/**
 * Runs: every batch, and one batch in detail. Polling backs off while nothing changes, stops when the batch is
 * finished, and pauses when the tab is hidden (lib/usePolling.js). "Unavailable" is never shown as "not assessed":
 * a store that cannot answer is an EmptyState or a degraded banner, never an empty list.
 */
export default function RunsPage({ batchId = null, onOpenBatch, onBack, onOpenClient }) {
  return (
    <div>
      <PageHeader
        eyebrow="Runs"
        title={batchId ? 'Run batch' : 'Runs'}
        sub={batchId ? null : 'Assessments and calculations queued for many clients, with progress, retry and cancel.'}
        icon={<ListChecks size={22} aria-hidden="true" />}
        back={batchId ? { label: 'All runs', onClick: onBack } : null}
      />
      {batchId
        ? <Detail batchId={batchId} onOpenClient={onOpenClient} />
        : <Card flush title="Batches"><BatchList onOpen={onOpenBatch} /></Card>}
    </div>
  );
}
