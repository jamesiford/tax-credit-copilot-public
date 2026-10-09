import { useEffect, useState } from 'react';
import { Check, Plus, TrendingUp } from 'lucide-react';
import { fetchClientEmployeeDrill, fetchWorkspaceEmployee, hasYear } from '../api.js';
import { MAX_STACK, stackEntry } from '../lib/whatIf.js';
import useWhatIfStack from './useWhatIfStack.js';
import { MONEY, monthLabel, shortHash, stageLabel } from '../lib/reference.js';
import InsightBar from './InsightBar.jsx';
import SortHeader from './SortHeader.jsx';
import { FilterBar } from './ColumnFilter.jsx';
import useTableControls from './useTableControls.js';
import { ENUM, NUMERIC, TEXT } from '../lib/gridFilter.js';
import PageHeader from './PageHeader.jsx';
import SectionTabs from './SectionTabs.jsx';
import { decisionBreakdown, employeeAnswer } from '../lib/answers.js';

/**
 * The drill's run identity has different field names from a Gold run envelope:
 * a calculation id rather than a run id, `created_at` rather than `produced_at`.
 * Feeding it to `provenanceLine` printed the bare word "Run".
 */
function employeeProvenance(data) {
  const run = data?.run;
  if (!run) return null;
  const parts = [];
  if (run.step1_calculation_id) parts.push(`Run ${shortHash(run.step1_calculation_id)}`);
  if (run.created_at) parts.push(`produced ${run.created_at}`);
  if (run.fiscal_begin) parts.push(`window ${run.fiscal_begin} → ${run.fiscal_end}`);
  if (run.step1_assumption_set_id) parts.push(`assumptions ${run.step1_assumption_set_id}`);
  if (run.code_commit) parts.push(`code ${String(run.code_commit).slice(0, 7)}`);
  if (run.data_source) parts.push(`source ${run.data_source}`);
  return parts.length ? parts.join(' · ') : null;
}

function Flag({ value, label }) {
  return <span className={`pill ${value ? 'pill-ok' : 'pill-warn'}`}>{label}: {value ? 'pass' : 'fail'}</span>;
}

function MethodCard({ title, method, thresholds }) {
  if (!method) return <div className="tcc-method-card"><h4>{title}</h4><p className="small muted">Not evaluated.</p></div>;
  const detail = method.denominator_detail || {};
  return (
    <div className="tcc-method-card">
      <div className="tcc-method-head">
        <h4>{title}</h4>
        <span className={`pill ${method.eligible ? 'pill-ok' : 'pill-warn'}`}>{method.eligible ? 'eligible' : 'not eligible'}</span>
      </div>
      <div className="tcc-method-metrics">
        <div><span>Denominator</span><b>{method.denominator_weeks} weeks</b></div>
        <div><span>Avg. hours</span><b>{method.rounded_avg_weekly_hours}</b><small>full {method.avg_weekly_hours}</small></div>
        <div><span>Avg. wages</span><b>{MONEY.format(Number(method.rounded_avg_weekly_wages))}</b><small>full {method.avg_weekly_wages}</small></div>
      </div>
      <div className="tcc-flag-row">
        <Flag value={method.passed_hours} label="Hours" />
        <Flag value={method.passed_wages} label="Wages" />
      </div>
      <p className="small muted">Rounded values tested at ≥ {thresholds.minimum_average_weekly_hours} hours and ≥ {MONEY.format(Number(thresholds.minimum_average_weekly_wages_usd))} wages.</p>
      <details className="tcc-detail-block">
        <summary>Denominator inputs</summary>
        <pre>{JSON.stringify(detail, null, 2)}</pre>
      </details>
    </div>
  );
}

/** How many periods each decision accounts for, and what each decision means. */
function DecisionSummary({ rows }) {
  const breakdown = decisionBreakdown(rows);
  if (breakdown.length < 2) return null;
  return (
    <div className="tcc-decision-summary">
      {breakdown.map(({ decision, count }) => (
        <span key={decision} className={`pill ${decision === 'included' ? 'pill-ok' : 'pill-neutral'}`}>
          {stageLabel(decision)}: {count}
        </span>
      ))}
    </div>
  );
}

const SOURCE_COLUMNS = {
  decision: {
    key: 'decision', label: 'Decision', type: ENUM, read: (r) => r.selection_decision,
    format: (v) => stageLabel(v),
  },
  source: { key: 'source', label: 'Source', type: TEXT, read: (r) => `${r.source_file}:${r.source_row}` },
  title: { key: 'title', label: 'Title', type: ENUM, read: (r) => r.job_title },
  unit: { key: 'unit', label: 'Unit', type: ENUM, read: (r) => r.unit_id },
  fein: { key: 'fein', label: 'FEIN', type: ENUM, read: (r) => r.fein },
  pps: { key: 'pps', label: 'PPS', type: TEXT, read: (r) => r.pay_period_start },
  ppe: { key: 'ppe', label: 'PPE', type: TEXT, read: (r) => r.pay_period_end },
  pay_date: { key: 'pay_date', label: 'Pay date', type: TEXT, read: (r) => r.pay_date },
  cadence: { key: 'cadence', label: 'Cadence', type: ENUM, read: (r) => r.pay_frequency_code },
  hours: { key: 'hours', label: 'Hours', type: NUMERIC, read: (r) => r.hours },
  wages: { key: 'wages', label: 'Wages', type: NUMERIC, read: (r) => r.wages },
};

function SourceRows({ rows }) {
  const table = useTableControls(SOURCE_COLUMNS, rows);
  return (
    <>
      <FilterBar {...table.bar('paychecks')} />
      <div className="tcc-table-wrap tcc-table-tall">
        <table className="tbl tcc-dense-table">
          <thead>
            <tr>
              {Object.keys(SOURCE_COLUMNS).map((key) => (
                <SortHeader key={key} {...table.head(key)} className={key === 'hours' || key === 'wages' ? 'num' : undefined} />
              ))}
            </tr>
          </thead>
          <tbody>{table.rows.map((row) => (
            <tr key={`${row.source_file}-${row.source_row}`}>
              <td><span className={`pill ${row.selection_decision === 'included' ? 'pill-ok' : 'pill-neutral'}`}>{stageLabel(row.selection_decision)}</span></td>
              <td className="small">{row.source_file}:{row.source_row}</td>
              <td>{row.job_title}</td>
              <td>{row.unit_id}</td><td>{row.fein}</td>
              <td>{row.pay_period_start}</td><td>{row.pay_period_end}</td><td>{row.pay_date}</td>
              <td>{row.pay_frequency_code}</td><td className="num">{row.hours}</td><td className="num">{MONEY.format(Number(row.wages))}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </>
  );
}

const MATRIX_COLUMNS = {
  unit: { key: 'unit', label: 'Unit', type: ENUM, read: (r) => r.unit_id },
  fein: { key: 'fein', label: 'FEIN', type: ENUM, read: (r) => r.fein },
  period: { key: 'period', label: 'Period', type: TEXT, read: (r) => r.period_start },
  source: { key: 'source', label: 'Source', type: NUMERIC, read: (r) => r.source_refs.length },
  counted: {
    key: 'counted', label: 'Counted', type: NUMERIC,
    read: (r) => r.months.reduce((total, value) => total + value, 0),
  },
};

function Matrix({ rows, months, flags }) {
  const table = useTableControls(MATRIX_COLUMNS, rows);
  if (!rows?.length) return <p className="small muted">This employee has no matrix rows under this method.</p>;
  return (
    <>
      {flags?.length > 0 && (
        <div className="callout warn"><b>{flags.length} test-of-twos disposition{flags.length === 1 ? '' : 's'}.</b> Raw and final cells remain visible below.</div>
      )}
      <FilterBar {...table.bar('segments')} />
      <div className="tcc-table-wrap">
        <table className="tbl tcc-matrix-table">
          <thead>
            <tr>
              <SortHeader {...table.head('unit')} />
              <SortHeader {...table.head('fein')} />
              <SortHeader {...table.head('period')} />
              <SortHeader {...table.head('source')} />
              {months.map((month) => <th key={month}>{monthLabel(month)}</th>)}
              <SortHeader {...table.head('counted')} />
            </tr>
          </thead>
          <tbody>{table.rows.map((row) => (
            <tr key={row.segment_id}>
              <td className="cell-strong">{row.unit_id}</td><td>{row.fein}</td>
              <td className="small">{row.period_start} → {row.period_end}</td>
              <td className="small">{row.source_refs.length} line{row.source_refs.length === 1 ? '' : 's'}</td>
              {row.months.map((value, index) => {
                const raw = row.raw_months[index];
                return <td key={months[index]} className={`tcc-matrix-cell ${value ? 'counted' : raw ? 'disposed' : ''}`}>{raw !== value ? `${raw}→${value}` : value}</td>;
              })}
              <td>{row.months.reduce((total, value) => total + value, 0)}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </>
  );
}

/**
 * Add this employee to the What-if stack (29 Sep), pre-filled with what the
 * rest of the year needs — the same reading Near the line shows. Only an open
 * year has a rest of it; otherwise the button says why it is not offered.
 */
function StackButton({ data, context, method = 'min_max', onOpenWhatIf }) {
  const stack = useWhatIfStack({ clientId: context.accountId, taxYear: Number(context.taxYear), method });
  const mm = data.step1?.min_max || data.step1?.pay_period;
  const row = {
    record_token: data.record_token,
    employee_id: data.employee_id,
    rest_of_year: data.rest_of_year,
    ...(data.where || {}),
    avg_weekly_hours: mm?.avg_weekly_hours,
    avg_weekly_wages: mm?.avg_weekly_wages,
    implied_hourly_rate: mm?.avg_weekly_hours ? mm.avg_weekly_wages / mm.avg_weekly_hours : null,
  };
  const entry = stackEntry(row);
  const stacked = stack.tokens.has(data.record_token);
  const why = {
    on_pace: 'Already on pace to clear both floors this year — nothing to add.',
    closed: 'The year is closed, so there is no rest of it to change.',
    no_payroll_to_date: 'No payroll by the checkpoint to take a pace from.',
  }[data.rest_of_year?.state] || 'No rest-of-year figure for this employee.';

  return (
    <div className="tcc-stack-actions">
      {stacked ? (
        <button
          type="button"
          className="btn btn-secondary prox-whatif on"
          onClick={() => stack.remove(data.record_token)}
          title="In the What-if stack — click to remove"
        >
          <Check size={14} /> In the What-if stack
        </button>
      ) : (
        <button
          type="button"
          className="btn btn-secondary"
          disabled={!entry || stack.entries.length >= MAX_STACK}
          onClick={() => stack.add([row])}
          title={entry
            ? `Pre-filled: +${entry.hours} hrs/wk${entry.raise ? ` and a $${entry.raise.toFixed(2)}/hr raise` : ''} for the rest of the year`
            : why}
        >
          <Plus size={14} /> Add to What-if
        </button>
      )}
      {stack.entries.length ? (
        <button type="button" className="btn btn-primary" onClick={() => (onOpenWhatIf ? onOpenWhatIf(stack.openHref) : window.location.assign(stack.openHref))}>
          <TrendingUp size={14} /> {stack.entries.length > 1 ? `Project all ${stack.entries.length}` : 'Project'} in What-if →
        </button>
      ) : null}
    </div>
  );
}

function PageFrame({ children }) {
  return <section className="tcc-drill-page">{children}</section>;
}

/**
 * The walk is a page, not an overlay. `selection_decision` needs the room:
 * "outside fiscal window", "shorter than seven days" and "filtered by pay code"
 * are three different explanations and a reviewer must tell them apart.
 */
export default function EmployeeDrill({ recordToken, context, method = 'min_max', onOpenWhatIf, onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState('source');

  useEffect(() => {
    let active = true;
    setData(null); setError(null);
    // A per-client token is minted for ONE tax year, so the drill cannot be
    // asked until that year is known. Opened cold from a URL, the shell's scope
    // holds `year: null` until the client's payroll resolves; posting then was
    // a 422 before every successful load. Wait instead — the loading line
    // already says what is happening.
    if (context && !hasYear(context.taxYear)) return () => { active = false; };
    // A token resolves only where the run that minted it is served. `context`
    // says which client-year opened this; without one it is the sealed run.
    const request = context
      ? fetchClientEmployeeDrill({ recordToken, ...context, taxYear: Number(context.taxYear) })
      : fetchWorkspaceEmployee(recordToken);
    request
      .then((result) => active && setData(result))
      .catch((reason) => active && setError(String(reason)));
    return () => { active = false; };
  }, [recordToken, context]);

  const tabs = [
    ['source', 'Paychecks'], ['eligibility', 'Eligibility'], ['min_max', 'Min-Max by month'],
    ['pay_period', 'Pay Period by month'], ['provenance', 'Audit trail'],
  ];

  const Frame = PageFrame;

  return (
    <Frame onClose={onClose}>
        <PageHeader
          eyebrow="Prove it"
          title={data?.employee_id || 'Loading employee…'}
          sub={data
            ? `Every paycheck behind this employee's ${data.program_code} TY${data.tax_year} result, and why each one counted or did not.`
            : 'Authorized employee calculation walk.'}
          actions={data && context?.accountId != null
            ? <StackButton data={data} context={context} method={method} onOpenWhatIf={onOpenWhatIf} />
            : null}
        />
        <SectionTabs tabs={tabs.map(([id, label]) => ({ id, label }))} active={tab} onChange={setTab} label="Employee walk" idPrefix="drill" />
        {/* 29 Sep: the banner is a quiet caption, and what this per-client walk
            cannot show moved behind the (i) — it was a paragraph above the
            paychecks it was about. */}
        {data ? (
          <InsightBar
            caption={employeeAnswer(data).replace(/\.$/, '')}
            notes={[
              data.not_available?.length
                ? `This is the run for ${data.program_code} TY${data.tax_year}, not the certified artifact. ${data.not_available.join(' ')}`
                : null,
              data.boundary
                ? 'Every inclusion and exclusion retains file and row lineage.'
                : 'Rows outside the fiscal window are shown and marked, because a missing month is usually a paycheck the window did not keep.',
              employeeProvenance(data),
            ]}
            request={context ? {
              page: 'employee', clientId: context.accountId, taxYear: context.taxYear,
              state: context.state, recordToken,
            } : null}
          />
        ) : null}
        <div className="tcc-drill-body">
          {error && <div className="callout warn">{error}</div>}
          {!data && !error && <div className="tcc-loading-inline">Loading the employee calculation…</div>}
          {data && tab === 'source' && (
            <>
              {/* `included` is a boolean and cannot say WHICH reason applied.
                  Three explanations, three different findings. */}
              <DecisionSummary rows={data.raw_source_rows} />
              {data.boundary && !data.boundary.boundary_complete && <div className="callout warn"><b>{stageLabel(data.boundary.status)}.</b> The source contains no valid pre-FY lookback; this employee&apos;s rows are shown exactly as supplied and no 52-week adjustment is fabricated.</div>}

              <SourceRows rows={data.raw_source_rows} />
            </>
          )}
          {data && tab === 'eligibility' && (
            <>
              <div className="tcc-total-band"><div><span>Common total hours</span><b>{data.step1.totals.total_hours}</b></div><div><span>Common total wages</span><b>{MONEY.format(Number(data.step1.totals.total_wages))}</b></div><div><span>{data.run.step1_assumption_set_id ? 'Step 1 assumptions' : 'Fiscal window'}</span><b>{data.run.step1_assumption_set_id || `${data.run.fiscal_begin} → ${data.run.fiscal_end}`}</b></div></div>
              <div className="tcc-method-grid"><MethodCard title="Min-Max" method={data.step1.min_max} thresholds={data.thresholds} /><MethodCard title="Pay Period" method={data.step1.pay_period} thresholds={data.thresholds} /></div>
              <section className={`tcc-invariant ${data.step1.denominator_invariant.pay_period_gt_min_max ? 'warn' : 'ok'}`}><div><b>Employee denominator invariant</b><span>Pay Period minus Min-Max weeks</span></div><div><strong>{data.step1.denominator_invariant.pay_period_minus_min_max_weeks ?? '—'}</strong><span>week delta</span></div><div><strong>{data.step1.denominator_invariant.over_review_tolerance ? 'Review' : 'Within tolerance'}</strong><span>1.5-week threshold</span></div><div><strong>{data.step1.denominator_invariant.pay_period_over_52_weeks ? 'Review' : 'Within max'}</strong><span>annual maximum control</span></div></section>
              {data.exceptions.step1.length > 0 && <div className="callout warn"><b>{data.exceptions.step1.length} Step 1 caveats remain visible.</b> {data.exceptions.step1.join(' ')}</div>}
              {(data.access_differences || []).length > 0 && <div className="panel"><h3 className="panel-title">Access differences</h3><pre>{JSON.stringify(data.access_differences, null, 2)}</pre></div>}
            </>
          )}
          {data && tab === 'min_max' && <Matrix rows={data.onezero?.min_max || []} months={data.onezero?.months || []} flags={(data.onezero?.overlap_flags || []).filter((flag) => flag.method === 'min_max')} />}
          {data && tab === 'pay_period' && <Matrix rows={data.onezero?.pay_period || []} months={data.onezero?.months || []} flags={(data.onezero?.overlap_flags || []).filter((flag) => flag.method === 'pay_period')} />}
          {data && tab === 'provenance' && (
            data.run.step1_calculation_id ? (
              <div className="tcc-provenance-grid">
                <div className="panel"><h3 className="panel-title">Run identity</h3><dl className="tcc-kv"><dt>Step 1 calculation</dt><dd>{data.run.step1_calculation_id}</dd><dt>Monthly employment calculation</dt><dd>{data.run.onezero_calculation_id}</dd><dt>Source manifest</dt><dd>{data.run.source_manifest_sha256}</dd><dt>Code commit</dt><dd>{data.run.code_commit}</dd><dt>Timestamp</dt><dd>{data.run.created_at}</dd></dl></div>
                <div className="panel"><h3 className="panel-title">Configuration</h3><dl className="tcc-kv"><dt>Step 1 assumptions</dt><dd>{data.run.step1_assumption_set_id}</dd><dt>Step 1 config hash</dt><dd>{data.run.step1_assumption_set_sha256}</dd><dt>Monthly employment assumptions</dt><dd>{data.run.onezero_assumption_set_id}</dd><dt>Monthly employment config hash</dt><dd>{data.run.onezero_assumption_set_sha256}</dd></dl><p className="small muted">Employee values remain in this authorized browser session and are never sent to Foundry.</p><details className="tcc-detail-block"><summary>Monthly employment caveats</summary><ul className="tcc-exception-list">{data.exceptions.onezero.map((exception) => <li key={exception}>{exception}</li>)}</ul></details></div>
              </div>
            ) : (
              <div className="tcc-provenance-grid">
                <div className="panel"><h3 className="panel-title">What was applied</h3><dl className="tcc-kv"><dt>Programme</dt><dd>{data.program_code}</dd><dt>Tax year</dt><dd>{data.tax_year}</dd><dt>Fiscal window</dt><dd>{data.run.fiscal_begin} → {data.run.fiscal_end}</dd><dt>Minimum weekly hours</dt><dd>{data.thresholds.minimum_average_weekly_hours}</dd><dt>Minimum weekly wages</dt><dd>{data.thresholds.minimum_average_weekly_wages_usd}</dd><dt>Payroll source</dt><dd>{data.run.data_source}</dd></dl></div>
                <div className="panel"><h3 className="panel-title">What this run cannot show</h3><ul className="tcc-exception-list">{data.not_available.map((item) => <li key={item}>{item}</li>)}</ul><p className="small muted">Employee values remain in this authorized browser session and are never sent to Foundry.</p></div>
              </div>
            )
          )}
        </div>
    </Frame>
  );
}
