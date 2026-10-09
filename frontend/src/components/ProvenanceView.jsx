import { useEffect, useState } from 'react';
import { AlertTriangle, CalendarRange, FileCheck2, Fingerprint, ShieldCheck } from 'lucide-react';
import { fetchWorkspaceAssumptions } from '../api.js';
import { MONEY, NUM, shortHash } from '../lib/reference.js';
import { PageHeader } from './ReferenceViews.jsx';

/**
 * Provenance — which run, which source, what was left alone.
 *
 * Lives under Defend because it answers the question an auditor asks rather
 * than one an operator asks: *how was this number produced, and can you produce
 * it again?* [UX-DIRECTION §4]
 *
 * Two of these panels were rescued from the retired Data Ingestion view. They
 * survived the editorial test where the rest of that view did not, and the
 * distinction is worth stating: row counts describe our machinery, but the
 * source manifest is what lets somebody re-run this, and the normalisation
 * controls are a claim that we did NOT quietly fix the data. A negative-hours
 * row is a payroll correction; silently dropping it would change a denominator.
 * Saying "we found four hundred and left every one alone" is a defensibility
 * statement, not a progress bar.
 *
 * Run identity came from the deleted Overview. UX-DIRECTION always said it
 * moved here; B4 removed Overview before that move happened, which briefly left
 * it with no home at all.
 */
export default function ProvenanceView({ summary, embedded = false }) {
  const [assumptions, setAssumptions] = useState(null);

  useEffect(() => {
    let cancelled = false;
    fetchWorkspaceAssumptions()
      .then((data) => { if (!cancelled) setAssumptions(data); })
      .catch(() => { /* the panel below degrades to the summary alone */ });
    return () => { cancelled = true; };
  }, []);

  const controls = summary.source.controls;
  const statutory = assumptions?.statutory;
  const equivalence = summary.equivalence;
  const fiscal = summary.fiscal;

  return <>
    {!embedded && (
      <PageHeader
        eyebrow="Prove it"
        title="Audit trail"
        sub="Which run produced these figures, from which source, under which statute — and what the engine deliberately left alone"
      />
    )}

    {equivalence && (
      <section className="panel">
        <h3 className="panel-title">
          <span><ShieldCheck size={15} /> Certified result</span>
          <span className="right">
            {equivalence.source_kind === 'lakehouse' ? 'reproduced from the lakehouse' : 'reproduced from source'}
          </span>
        </h3>
        <p className="small muted">
          The figures reconciled against an independent reference
          implementation between 30 July and 24 August 2026.
          This run recomputed them from
          {equivalence.source_kind === 'lakehouse'
            ? ' the Fabric lakehouse, not from the reconciliation extract'
            : ' the reconciliation extract'}
          {' '}— a source that does not reproduce them is refused rather than
          shown under this heading.
        </p>
        <table className="tbl">
          <thead>
            <tr><th>Measure</th><th>Certified</th><th>This run</th><th>&nbsp;</th></tr>
          </thead>
          <tbody>
            {[
              ['Employees evaluated', 'employees_evaluated'],
              ['Eligible — Min-Max', 'min_max_eligible'],
              ['Eligible — Pay Period', 'pay_period_eligible'],
            ].map(([label, key]) => {
              const agrees = equivalence.expected[key] === equivalence.observed[key];
              return (
                <tr key={key}>
                  <td>{label}</td>
                  <td>{NUM.format(equivalence.expected[key])}</td>
                  <td><b>{NUM.format(equivalence.observed[key])}</b></td>
                  <td className={agrees ? 'pill-ok' : 'pill-warn'}>
                    {agrees ? 'agrees' : 'DIVERGED'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    )}

    <div className="grid-2 tcc-overview-grid">
      <section className="panel">
        <h3 className="panel-title">
          <span><Fingerprint size={15} /> Run identity</span>
          <span className="right">sealed &amp; reproducible</span>
        </h3>
        <dl className="tcc-kv">
          <dt>Step 1 run</dt>
          <dd title={summary.run.step1_calculation_id}>{shortHash(summary.run.step1_calculation_id, 18)}</dd>
          <dt>Monthly employment run</dt>
          <dd title={summary.run.onezero_calculation_id}>{shortHash(summary.run.onezero_calculation_id, 18)}</dd>
          <dt>Source manifest</dt>
          <dd title={summary.run.source_manifest_sha256}>{shortHash(summary.run.source_manifest_sha256, 18)}</dd>
          <dt>Step 1 config</dt>
          <dd>{summary.run.step1_assumption_set_id}</dd>
          <dt>Monthly employment config</dt>
          <dd>{summary.run.onezero_assumption_set_id}</dd>
          <dt>Code commit</dt>
          <dd>{shortHash(summary.run.code_commit, 10)}</dd>
          <dt>Source</dt>
          <dd>{summary.run.source_kind === 'lakehouse' ? 'Fabric lakehouse' : 'Reconciliation extract (CSV)'}</dd>
          <dt>Created</dt>
          <dd>{new Date(summary.run.created_at).toLocaleString()}</dd>
        </dl>
      </section>

      <section className="panel">
        <h3 className="panel-title">
          <span><ShieldCheck size={15} /> Statute applied</span>
          <span className="right">resolved per tax year</span>
        </h3>
        {statutory ? <>
          <dl className="tcc-kv">
            <dt>Program</dt><dd>{statutory.program_code}</dd>
            <dt>Tax year</dt><dd>{statutory.tax_year}</dd>
            <dt>Weekly hours floor</dt><dd>{statutory.minimum_average_weekly_hours}</dd>
            <dt>Weekly wage floor</dt><dd>{MONEY.format(statutory.minimum_average_weekly_wages_usd)}</dd>
            <dt>Lowest-wage county</dt><dd>{statutory.lowest_wage_county || '—'}</dd>
            <dt>DOL report year</dt><dd>{statutory.dol_report_year ?? '—'}</dd>
            <dt>Resolved from</dt><dd>{statutory.source}</dd>
          </dl>
          {statutory.prototype_verify && (
            <div className="callout warn">
              <b>Unverified placeholder.</b> This year&apos;s floor has not been
              confirmed against the published wage table and must not reach a
              client figure.
            </div>
          )}
          <p className="small muted">
            The floor is a fact about the tax year, not a choice we made, so it is
            resolved from the year&apos;s rule pack rather than carried in the
            assumption set. Each year of a retroactive audit runs under its own.
          </p>
        </> : <p className="small muted">Loading resolved statute…</p>}
      </section>
    </div>

    {fiscal && (
      <section className="panel">
        <h3 className="panel-title">
          <span><CalendarRange size={15} /> Fiscal year</span>
          <span className="right">
            {fiscal.applied.basis === 'client_rules' ? 'a fact, not a derivation' : 'assumed'}
          </span>
        </h3>
        <dl className="tcc-kv">
          <dt>Window measured</dt>
          <dd>{fiscal.applied.begin} → {fiscal.applied.end}</dd>
          <dt>Tax year</dt>
          <dd>
            {fiscal.tax_year_applied}
            {' — labelled by the year it '}
            <b>{fiscal.convention.label}</b>
            {fiscal.convention.regulation ? `, per ${fiscal.convention.regulation}` : ''}
          </dd>
          <dt>Window source</dt>
          <dd>{fiscal.applied.note}</dd>
          <dt>Client&apos;s own rule</dt>
          <dd>
            {fiscal.from_source_system.basis === 'client_rules'
              ? `${fiscal.from_source_system.begin} → ${fiscal.from_source_system.end}`
              : 'not on file for this source — calendar year would be assumed'}
            {fiscal.agrees_with_source ? ' · agrees' : ''}
          </dd>
        </dl>
        {fiscal.applied.convention_matters && (
          <p className="small muted">
            This is not a calendar year, so the labelling convention decides the
            answer. Under <b>begins</b> it is TY{fiscal.applied.tax_year_if_labelled_by_begin};
            under <b>ends</b> it would be TY{fiscal.applied.tax_year_if_labelled_by_end},
            which would price it under a different year&apos;s wage floor.
          </p>
        )}
        {fiscal.convention.unconfirmed && (
          <div className="callout warn">
            <AlertTriangle size={16} />
            <b>Read from the regulation, not yet confirmed.</b> Georgia
            110-9-1-.02(1)(a) labels a tax year by the year it begins, and the
            certified run is consistent with that. It has not been confirmed with
            the partner, so it is flagged rather than treated as settled.
          </div>
        )}
      </section>
    )}

    <section className="panel">
      <h3 className="panel-title">
        <span><FileCheck2 size={15} /> Source manifest</span>
        <span className="right">{shortHash(summary.run.source_manifest_sha256, 18)}</span>
      </h3>
      <p className="small muted">
        The exact bytes this run read. A figure that cannot name its source cannot
        be reproduced, and a reproduction that reads different bytes is not one.
      </p>
      <div className="tcc-file-grid">
        {summary.source.files.map((file, index) => (
          <div className="tcc-file-card" key={file.file_name}>
            <span>{file.lineage ? `Delta v${file.lineage.version}` : `Chunk ${index + 1}`}</span>
            <b>{file.file_name}</b>
            <small>
              {NUM.format(file.usable_rows)} usable
              {' · '}
              {file.lineage
                ? `${NUM.format(file.lineage.files)} parquet files`
                : `${NUM.format(file.padded_rows)} padded`}
            </small>
            <code>{shortHash(file.sha256, 14)}</code>
          </div>
        ))}
      </div>
      {summary.source.source_kind === 'lakehouse' && (
        <p className="small muted">
          Read from the lakehouse, so the reproducibility anchor is a Delta
          version rather than a file hash. The digest above is taken over the
          projected rows in order, which is what makes it a claim rather than a
          pointer.
        </p>
      )}
    </section>

    <section className="panel">
      <h3 className="panel-title">
        <span>What the engine left alone</span>
        <span className="right">nothing is silently repaired</span>
      </h3>
      <p className="small muted">
        Each of these is a source anomaly the engine could have quietly fixed and
        did not. A negative-hours line is a payroll correction; dropping it would
        change a denominator without anyone deciding to.
      </p>
      <div className="tcc-control-grid">
        <div><span>Zero-hour rows</span><b>{NUM.format(controls.zero_hour_rows)}</b><small>signed wages retained</small></div>
        <div><span>Negative hours</span><b>{NUM.format(controls.negative_hour_rows)}</b><small>corrections preserved</small></div>
        <div><span>Negative wages</span><b>{NUM.format(controls.negative_wage_rows)}</b><small>corrections preserved</small></div>
        <div><span>Pay date before PPE</span><b>{NUM.format(controls.pay_date_before_period_end_rows)}</b><small>flagged source anomaly</small></div>
      </div>
    </section>

    <section className="panel">
      <h3 className="panel-title">
        <span><AlertTriangle size={15} /> Standing caveats</span>
        <span className="right">what this run does not claim</span>
      </h3>
      <p className="small muted">
        Limits of the current run, stated rather than implied. These were
        previously visible only inside a per-employee drill, which meant a
        caveat about the whole calculation was reachable only by opening one
        person — so most people never saw it.
      </p>
      {(summary.exceptions?.step1 || []).length + (summary.exceptions?.onezero || []).length === 0
        ? <p className="small">No outstanding caveats on this run.</p>
        : <ul className="tcc-exception-list">
            {(summary.exceptions?.step1 || []).map((e) => <li key={e}><b>Step 1</b> {e}</li>)}
            {(summary.exceptions?.onezero || []).map((e) => <li key={e}><b>Monthly employment</b> {e}</li>)}
          </ul>}
    </section>

    <div className="callout info">
      <b>Per-row lineage lives on the employee.</b> Every included and excluded
      paycheck line keeps its file and row number; open any employee from
      Eligibility to see theirs. A searchable dump of all {NUM.format(controls.usable_rows)} rows
      was removed — it showed the machinery rather than the decision.
    </div>
  </>;
}
