import { useEffect, useState } from 'react';
import { FileCheck2, Loader2, Printer, ShieldCheck } from 'lucide-react';
import { fetchWorkspaceAssumptions, fetchWorkspaceCalculationWalk } from '../api.js';
import { NUM } from '../lib/reference.js';
import { CalculationWalkView, PageHeader } from './ReferenceViews.jsx';
import ProvenanceView from './ProvenanceView.jsx';

/**
 * The evidence pack — what a client or an examiner is actually handed.
 *
 * This used to render `/api/evidence`, which derives packs from five static
 * claims left over from the synthetic demo: South Carolina, Tennessee,
 * Virginia, federal WOTC. None of those clients exist in this book and none of
 * those programs have authored statute, so the page advertised five audit
 * dossiers the system could not produce.
 *
 * It now renders the one pack that is real: the certified run. Every figure on
 * it is hashed, every step names the assumption it applied, and the whole thing
 * prints — which is the actual deliverable, because the person who needs it
 * wants a PDF in a file rather than a dashboard.
 *
 * Provenance and Calculation walk used to be their own nav entries. All three
 * read the same two singleton endpoints, and this page already carried a
 * summary of both — a hashes panel that repeated run identity value for value,
 * and a walk table that repeated the walk. Three entries for one dossier makes
 * a reader hunt for the page with the answer on it. They are sections here now,
 * with the full working behind a toggle so the printed pack stays the length of
 * a printed pack.
 */

function Row({ label, children }) {
  return <><dt>{label}</dt><dd>{children}</dd></>;
}

export default function EvidenceView({ summary, onAskCopilot }) {
  const [walk, setWalk] = useState(null);
  const [assumptions, setAssumptions] = useState(null);
  const [loading, setLoading] = useState(true);
  const [fullWorking, setFullWorking] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetchWorkspaceCalculationWalk().catch(() => null),
      fetchWorkspaceAssumptions().catch(() => null),
    ])
      .then(([w, a]) => { if (!cancelled) { setWalk(w); setAssumptions(a); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const run = summary.run;
  const controls = summary.source.controls;
  const statutory = assumptions?.statutory;
  const eligibility = summary.eligibility || {};
  const steps = walk?.steps || [];

  return <>
    <PageHeader
      eyebrow="Prove it"
      title="Audit trail"
      sub="The sealed dossier for this run — identity, statute, source, result, and every step that produced it"
      actions={<>
        <button className="btn btn-secondary" onClick={() => window.print()}>
          <Printer size={15} /> Print / Save PDF
        </button>
        {onAskCopilot && (
          <button
            className="btn btn-primary"
            onClick={() => onAskCopilot('What is inside this audit trail, and what makes the calculation reproducible under audit?')}
          >
            Ask Copilot
          </button>
        )}
      </>}
    />

    <div className="callout info">
      <b>One audit trail, because there is one certified run.</b> A trail is only worth
      handing over if every figure in it can be re-derived, so this page shows
      the run that can be — not a list of dossiers we would have to build first.
    </div>

    <div className="grid-2 tcc-overview-grid">
      <section className="panel">
        <h3 className="panel-title">
          <span><FileCheck2 size={15} /> Cover sheet</span>
          <span className="right">sealed</span>
        </h3>
        <dl className="tcc-kv">
          <Row label="Client">{summary.workspace?.client_name || 'Reference Dataset Client'}</Row>
          <Row label="Program">{statutory?.program_code || '—'}</Row>
          <Row label="Tax year">{statutory?.tax_year || eligibility?.thresholds?.source_tax_year || '—'}</Row>
          <Row label="Source">{run.source_kind === 'lakehouse' ? 'Fabric lakehouse' : 'Reconciliation extract (CSV)'}</Row>
          <Row label="Payroll rows">{NUM.format(controls.usable_rows)}</Row>
          <Row label="Prepared">{new Date(run.created_at).toLocaleString()}</Row>
        </dl>
      </section>

      <section className="panel">
        <h3 className="panel-title">
          <span><ShieldCheck size={15} /> Result</span>
          <span className="right">{summary.equivalence?.matches ? 'reproduces the certified figures' : 'see run identity below'}</span>
        </h3>
        {/* The floors and the statute path used to sit here too. They are the
            Statute applied panel's job, and a floor quoted in two places is a
            floor somebody has to check agrees with itself. */}
        <dl className="tcc-kv">
          <Row label="Employees evaluated">{NUM.format(controls.distinct_employees)}</Row>
          <Row label="Eligible — Min-Max">{NUM.format(eligibility.min_max?.eligible_employees ?? 0)}</Row>
          <Row label="Eligible — Pay Period">{NUM.format(eligibility.pay_period?.eligible_employees ?? 0)}</Row>
        </dl>
      </section>
    </div>

    {/* Run identity, statute, fiscal window, source manifest, the controls the
        engine did not apply, and the standing caveats. This page used to carry
        a Hashes panel that repeated the first of those value for value. */}
    <ProvenanceView summary={summary} embedded />

    <section className="panel">
      <h3 className="panel-title">
        <span>Calculation walk</span>
        <span className="right">
          {steps.length} step{steps.length === 1 ? '' : 's'}
          {' · '}
          <button
            type="button"
            className="tcc-link"
            onClick={() => setFullWorking((on) => !on)}
          >
            {fullWorking ? 'summary' : 'full working'}
          </button>
        </span>
      </h3>
      {loading && <div className="callout info"><Loader2 size={15} className="spin" /> Reading the walk…</div>}
      {!loading && !steps.length && <p className="small muted">No recorded walk for this run.</p>}
      {steps.length > 0 && !fullWorking && (
        <table className="tbl">
          <thead>
            <tr><th>Step</th><th>Stage</th><th>Formula</th><th>Assumptions</th><th>Citation</th></tr>
          </thead>
          <tbody>
            {steps.map((s) => (
              <tr key={s.step_id}>
                <td className="small"><code>{s.step_id}</code></td>
                <td className="small">{s.stage}{s.method && s.method !== 'shared' ? ` · ${s.method}` : ''}</td>
                <td className="small">{s.formula}</td>
                <td className="small">{(s.assumption_ids || []).join(', ') || '—'}</td>
                <td className="small">{s.citation || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="small muted">
        Every step names the assumption it applied and the clause it came from.
        The summary is the version that fits on a printed page; full working adds
        the inputs, parameters and output of each step.
      </p>
    </section>

    {/* Outside the panel: the walk renders its own sections and would nest. */}
    {fullWorking && steps.length > 0 && <CalculationWalkView embedded />}
  </>;
}
