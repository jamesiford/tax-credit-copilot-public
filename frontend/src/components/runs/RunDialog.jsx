import { Play, X } from 'lucide-react';
import { useMemo, useRef, useState, useEffect } from 'react';
import { previewRunBatch, startRunBatch } from '../../api.js';
import useModal from '../ask/useModal.js';
import Button from '../ui/Button.jsx';
import Callout from '../ui/Callout.jsx';
import Skeleton from '../ui/Skeleton.jsx';
import {
  KINDS, allClientsNote, confirmationOk, newIdempotencyKey, previewLines, refreshOnceNote, runLabel, scopeFor, startBody,
} from '../../lib/runBatches.js';
import './runs.css';

const PREVIEW_DELAY_MS = 250;

function describeError(error) {
  return {
    title: error?.reason || error?.message || 'The request was refused.',
    remedy: error?.remedy || 'Nothing was queued. Adjust the request and try again.',
  };
}

function FirstItems({ items }) {
  if (!items?.length) return null;
  return (
    <table className="tbl-compact runs-first" aria-label="First clients in this batch">
      <thead><tr><th>Client</th><th>Last run</th></tr></thead>
      <tbody>
        {items.map((item) => (
          <tr key={item.client_id}>
            <td>{item.client_name || `Account ${item.client_id}`}</td>
            <td className="small">
              {item.last_run?.state === 'never_run'
                ? 'Never calculated'
                : `TY${item.last_run?.tax_year ?? '—'}${item.last_run?.completed_at ? `, ${item.last_run.completed_at.slice(0, 10)}` : ''}`}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Unavailable({ list }) {
  if (!list?.length) return null;
  return (
    <Callout tone="partial" title={`${list.length} unavailable`}>
      <p>Whether these were assessed is unknown right now. That is not &ldquo;not assessed&rdquo;.</p>
      <ul>
        {list.slice(0, 10).map((u) => (
          <li key={u.client_id}>{u.client_name || `Account ${u.client_id}`}: {u.reason || u.dependency}</li>
        ))}
      </ul>
    </Callout>
  );
}

function Preview({ state, scope }) {
  if (state.loading) return <Skeleton lines={4} label="Previewing what would run" />;
  if (state.error) {
    const { title, remedy } = describeError(state.error);
    return (
      <Callout tone="partial" title="The preview is unavailable">
        <p>{title}</p>
        <p>{remedy} Nothing was changed.</p>
      </Callout>
    );
  }
  const p = state.preview;
  if (!p) return null;
  return (
    <div className="runs-preview" aria-live="polite">
      <ul className="runs-lines">
        {previewLines(p).map((line) => <li key={line}>{line}</li>)}
        <li>{refreshOnceNote(p.refresh_once)}</li>
      </ul>
      {allClientsNote(scope) ? <Callout tone="partial" title="Every client">{allClientsNote(scope)}</Callout> : null}
      {p.over_size_limit ? (
        <Callout tone="below-min" title="Over the size limit">
          This selects {p.items} runs and the limit is {p.max_items}. Narrow the selection.
        </Callout>
      ) : null}
      <Unavailable list={p.unavailable} />
      <FirstItems items={p.first_items} />
      {(p.notes || []).map((note) => <p key={note} className="small muted">{note}</p>)}
    </div>
  );
}

function Options({ o, set, programs, authoredYears }) {
  const toggleYear = (y) => set.years((cur) => (cur.includes(y) ? cur.filter((v) => v !== y) : [...cur, y].sort()));
  return (
    <>
      <fieldset className="runs-field">
        <legend>What to run</legend>
        <div className="runs-choices">
          {KINDS.map((k) => (
            <label key={k.id} className="runs-choice">
              <input type="radio" name="run-kind" value={k.id} checked={o.kind === k.id} onChange={() => set.kind(k.id)} />
              <span><b>{k.label}</b> <span className="muted small">{k.hint}</span></span>
            </label>
          ))}
        </div>
      </fieldset>
      <label className="runs-field">
        <span>Program</span>
        <select value={o.programCode} onChange={(e) => set.programCode(e.target.value)}>
          <option value="">Automatic (every program with statute for the client)</option>
          {programs.map((p) => <option key={p.program_code} value={p.program_code}>{p.name || p.program_code}</option>)}
        </select>
      </label>
      <fieldset className="runs-field">
        <legend>Tax years</legend>
        <p className="small muted">None chosen: each client&rsquo;s latest runnable year.</p>
        <div className="runs-years">
          {authoredYears.map((y) => (
            <label key={y} className="runs-year">
              <input type="checkbox" checked={o.years.includes(y)} onChange={() => toggleYear(y)} /> TY{y}
            </label>
          ))}
        </div>
      </fieldset>
      <label className="runs-choice">
        <input type="checkbox" checked={o.skipUnchanged} onChange={(e) => set.skipUnchanged(e.target.checked)} />
        <span><b>Skip clients whose data and rules are unchanged</b> <span className="muted small">Off by default, so every client runs. When on, a client is skipped only if all its authored-year payroll, the assumptions and the rule pack match its last run.</span></span>
      </label>
      <label className="runs-choice">
        <input type="checkbox" checked={!o.refreshOnce} disabled={!o.years.length} onChange={(e) => set.refreshOnce(!e.target.checked)} />
        <span><b>One run per client and year</b> <span className="muted small">Needs tax years. Each run refreshes every year, so the cost is multiplied.</span></span>
      </label>
    </>
  );
}

const DEFAULTS = { kind: 'calculate', programCode: '', years: [], skipUnchanged: false, refreshOnce: true };

/**
 * "Run for N clients". The preview comes first and is never skipped: it is requested as soon as the dialog opens
 * and again whenever an option changes, and Start stays disabled until a preview of the CURRENT options is on
 * screen. A start sends one idempotency key for the life of the dialog, so a double click queues one batch.
 */
export default function RunDialog({ open, selection, scopeOptions, onClose, onStarted }) {
  const dialogRef = useRef(null);
  const [key, setKey] = useState(null);
  const [o, setO] = useState(DEFAULTS);
  const [typed, setTyped] = useState('');
  const [state, setState] = useState({ loading: true, preview: null, error: null });
  const [submitting, setSubmitting] = useState(false);
  const [refusal, setRefusal] = useState(null);
  useModal(dialogRef, { open, onClose, fallbackId: 'run-selection-open' });

  const set = useMemo(() => Object.fromEntries(Object.keys(DEFAULTS).map((field) => [
    field, (value) => setO((cur) => ({ ...cur, [field]: typeof value === 'function' ? value(cur[field]) : value })),
  ])), []);

  useEffect(() => {
    if (!open) return;
    setKey(newIdempotencyKey());
    setO(DEFAULTS); setTyped(''); setRefusal(null); setSubmitting(false);
  }, [open]);

  const body = useMemo(() => startBody({
    selection, kind: o.kind, programCode: o.programCode || null, taxYears: o.years, skipUnchanged: o.skipUnchanged,
    refreshOnce: o.years.length ? o.refreshOnce : true,
  }), [selection, o]);

  useEffect(() => {
    if (!open) return undefined;
    let cancelled = false;
    setState((prev) => ({ ...prev, loading: true, error: null }));
    const timer = setTimeout(() => {
      previewRunBatch(body)
        .then((r) => { if (!cancelled) setState({ loading: false, preview: r.preview, error: null }); })
        .catch((e) => { if (!cancelled) setState({ loading: false, preview: null, error: e }); });
    }, PREVIEW_DELAY_MS);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [open, body]);

  const { preview } = state;
  const needsTyped = Boolean(preview?.requires_confirmation);
  const canStart = Boolean(preview) && !state.loading && preview.items > 0 && !preview.over_size_limit
    && confirmationOk(preview, typed) && !submitting;

  async function start() {
    setSubmitting(true);
    setRefusal(null);
    try {
      const batch = await startRunBatch({ ...body, idempotency_key: key, ...(needsTyped ? { confirm_items: Number(typed) } : {}) });
      onStarted?.(batch);
    } catch (e) {
      setRefusal(e);
      setSubmitting(false);
    }
  }

  if (!open) return null;
  return (
    <div className="runs-overlay">
      <div className="runs-scrim" aria-hidden="true" onClick={onClose} />
      <div ref={dialogRef} className="runs-dialog" role="dialog" aria-modal="true" aria-labelledby="runs-dialog-title">
        <header className="runs-head">
          <h2 id="runs-dialog-title">{runLabel(selection)}</h2>
          <Button size="sm" variant="ghost" onClick={onClose} aria-label="Close" icon={<X size={16} />} />
        </header>
        <div className="runs-body">
          <Options
            o={o} set={set} authoredYears={scopeOptions?.years?.authored || []}
            programs={(scopeOptions?.programs || []).filter((p) => (p.authored_years || []).length)}
          />
          <h3 className="runs-subhead">What this would do</h3>
          <Preview state={state} scope={scopeFor(selection)} />
          {needsTyped ? (
            <label className="runs-field runs-confirm">
              <span>This starts {preview.items} runs, above {preview.confirm_above}. Type <b>{preview.items}</b> to confirm.</span>
              <input
                type="text" inputMode="numeric" autoComplete="off" value={typed} data-autofocus
                onChange={(e) => setTyped(e.target.value)} aria-label={`Type ${preview.items} to confirm`}
              />
            </label>
          ) : null}
          {refusal ? (
            <Callout tone="below-min" title="Not started">
              <p>{describeError(refusal).title}</p>
              <p>{describeError(refusal).remedy}</p>
            </Callout>
          ) : null}
        </div>
        <footer className="runs-foot">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="primary" icon={<Play size={14} />} disabled={!canStart} loading={submitting} onClick={start}>
            Start {preview ? `${preview.items} run${preview.items === 1 ? '' : 's'}` : ''}
          </Button>
        </footer>
      </div>
    </div>
  );
}
