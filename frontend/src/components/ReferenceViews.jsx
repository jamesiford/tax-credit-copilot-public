import { Fragment, useEffect, useState } from 'react';
import { FileSearch, Search } from 'lucide-react';
import {
  fetchEligibility,
  fetchOneZeroMatrix,
  fetchWorkspaceAssumptions,
  fetchWorkspaceCalculationWalk,
  fetchWorkspaceComparison,
  fetchWorkspaceComparisonStage,
  fetchWorkspaceContributors,
  fetchWorkspaceOneZero,
  isCalculated,
  searchWorkspaceEligibility,
} from '../api.js';
import { assumptionEntries, eligibilityLabel, MONEY, monthLabel, NUM, shortHash, stageLabel, statusTone } from '../lib/reference.js';
import { PORTFOLIO } from '../lib/scopeDimension.js';
import PageHeader from './PageHeader.jsx';
import SortHeader from './SortHeader.jsx';
import { FilterBar } from './ColumnFilter.jsx';
import useTableControls from './useTableControls.js';
import { ENUM, NUMERIC, TEXT } from '../lib/gridFilter.js';

// Re-exported because three sibling views import it from here. There was a
// SECOND PageHeader defined in this file, with its own prop name and its own
// classes, so the app shipped two header treatments kept in step by hand.
export { default as PageHeader } from './PageHeader.jsx';

/** The eligibility table's headers; a key means the server can sort by it. */
const ELIGIBILITY_HEADS = [
  ['employee_id', 'Employee'], ['status', 'Status'], ['near_floor', 'Proximity'],
  ['total_hours', 'Total hrs', 'num'], ['total_wages', 'Total wages', 'num'],
  ['mm_weeks', 'MM weeks', 'num'], ['mm_hours', 'MM hrs / wages', 'num'], [null, 'MM tests'],
  ['pp_weeks', 'PP weeks', 'num'], ['pp_hours', 'PP hrs / wages', 'num'], [null, 'PP tests'],
];

/** Monthly employment's unit summary, filtered and sorted in the browser (101 rows). */
const UNIT_SUMMARY_COLUMNS = {
  unit: { key: 'unit', label: 'Unit', type: TEXT, read: (r) => r.unit_id },
  fein: { key: 'fein', label: 'FEIN', type: ENUM, read: (r) => r.fein },
  total: { key: 'total', label: 'Total', type: NUMERIC, read: (r) => r.total },
  average: { key: 'average', label: 'Average', type: NUMERIC, read: (r) => r.average_headcount },
  unrounded: { key: 'unrounded', label: 'Full precision', type: NUMERIC, read: (r) => r.unrounded_average },
  source_rounded: { key: 'source_rounded', label: 'Source rounded', type: NUMERIC, read: (r) => r.source_rounded_average },
  application: { key: 'application', label: 'App 2dp', type: NUMERIC, read: (r) => r.application_average },
};

const OVERLAP_COLUMNS = {
  employee: { key: 'employee', label: 'Employee', type: TEXT, read: (f) => f.employee_id },
  month: { key: 'month', label: 'Month', type: NUMERIC, read: (f) => f.month_index + 1 },
  candidates: { key: 'candidates', label: 'Candidates', type: NUMERIC, read: (f) => f.candidate_segment_ids.length },
  kept: { key: 'kept', label: 'Kept segment', type: TEXT, read: (f) => f.kept_segment_id },
  basis: { key: 'basis', label: 'Basis', type: TEXT, read: (f) => f.decision_basis },
};

function Status({ status, children }) {
  return <span className={`tcc-status ${statusTone(status)}`}>{children || stageLabel(status)}</span>;
}

function Kpi({ label, value, sub, tone = '', onClick }) {
  const content = <><div className="kpi-label">{label}</div><div className="kpi-value">{value}</div><div className="kpi-sub">{sub}</div></>;
  return onClick
    ? <button type="button" className={`kpi-card tcc-kpi-button ${tone}`} onClick={onClick}>{content}</button>
    : <div className={`kpi-card ${tone}`}>{content}</div>;
}

function Pager({ total, offset, limit, onChange }) {
  if (total <= limit) return null;
  return <div className="tcc-pager"><button className="btn btn-secondary" disabled={!offset} onClick={() => onChange(Math.max(0, offset - limit))}>Previous</button><span>{NUM.format(offset + 1)}–{NUM.format(Math.min(offset + limit, total))} of {NUM.format(total)}</span><button className="btn btn-secondary" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>Next</button></div>;
}

export function EligibilityView({ summary, openEmployee, scope }) {
  const [data, setData] = useState(null); const [error, setError] = useState(null);
  const [status, setStatus] = useState('all'); const [proximity, setProximity] = useState('all');
  const [query, setQuery] = useState(''); const [offset, setOffset] = useState(0); const limit = 50;
  // Sorted by the SERVER before the page is cut; filtered by the status tabs,
  // the near-floor toggle and the id search above the table.
  const [sort, setSort] = useState([{ key: 'employee_id', desc: false }]);
  const clientId = scope?.clientId; const year = scope?.year; const jurisdiction = scope?.jurisdiction || 'GA';
  // A token resolves only where the run that minted it is served. These rows are
  // minted per client-year, so the drill has to be told which one.
  const drillContext = { taxYear: year, state: jurisdiction, accountId: clientId };
  // `PORTFOLIO` is a string sentinel, not an id. Sending it as `account_id`
  // is a 422, and "who qualifies across every client" is not a question the
  // statute answers — eligibility is tested per employee within one fiscal year.
  const isPortfolio = clientId === PORTFOLIO;
  useEffect(() => {
    if (year == null || isPortfolio) return undefined;
    const timer = setTimeout(() => {
      setError(null);
      fetchEligibility(year, {
        state: jurisdiction, accountId: clientId, status, nearFloor: proximity === 'near_floor',
        q: query, limit, offset, sort: sort[0]?.key, order: sort[0]?.desc ? 'desc' : 'asc',
      }).then(setData).catch((err) => { setData(null); setError(err.message); });
    }, 180);
    return () => clearTimeout(timer);
  }, [year, clientId, jurisdiction, query, status, proximity, offset, sort]);
  const options = [['all', 'All'], ['both', 'Both'], ['min_max_only', 'Min-Max only'], ['pay_period_only', 'Pay Period only'], ['neither', 'Neither']];
  // Source-quality controls describe the SEALED snapshot, so they render only
  // when the selected client is the one that snapshot is of. Showing them under
  // another client would attribute one client's exceptions to another.
  const sealedAccount = summary?.workspace?.account_id;
  const showSourceControls = summary != null
    && (clientId == null || String(clientId) === String(sealedAccount));
  const periods = summary?.eligibility?.pay_period_controls;
  const floors = data?.thresholds;
  // `isCalculated` is the ONE place "we have not looked" is told apart from
  // "we looked and found nothing". A view must never decide it by counting rows.
  const calculated = isCalculated(data);
  const uncalculated = data != null && !calculated;
  return <>
    <PageHeader eyebrow="What is it worth" title="Eligibility" sub="One employee total · two independent denominators · two independently validated eligibility lists" />
    <div className="callout info"><b>Methods are not expected to agree with each other.</b> Min-Max and Pay Period must each agree with the partner’s implementation of that method.</div>
    <div className="tcc-formula-pair"><div><b>Min-Max denominator</b><code>weeks = (last PPE - first PPS) / 7</code><span>BA-11 · exclusive days · zero-hour rows included in span</span></div><div><b>Pay Period denominator</b><code>weeks = Σ (PPE - PPS + 1) / 7</code><span>BA-03 · actual period span · PayFrequency is lineage only</span></div></div>
    {isPortfolio && <div className="callout info">Eligibility is tested per employee against one client’s fiscal year, so there is no portfolio-wide population to show. Select a client to see theirs.</div>}
    {error && <div className="callout warn"><b>No population for this selection.</b> {error}</div>}
    {!isPortfolio && !data && !error && <div className="panel tcc-loading-inline">Reading this client’s population from the warehouse…</div>}
    {/* The population is READ from the run that decided it, so a client-year no
        run has reached carries no figure. Rendering zeroes here would say the
        payroll was examined and nobody qualified. */}
    {uncalculated && (
      <div className="panel">
        <h2 className="panel-title">Awaiting the next run</h2>
        <p className="page-sub">{data.message}</p>
      </div>
    )}
    {calculated && <>
      <div className="kpi-strip tcc-kpi-4"><Kpi label="Employees evaluated" value={NUM.format(data.employees_evaluated)} sub={`${data.state} · TY${data.tax_year}`} /><Kpi label="Eligible" value={`${NUM.format(data.min_max_eligible)} / ${NUM.format(data.pay_period_eligible)}`} sub={`Min-Max / Pay Period · ${NUM.format(data.reconciliation.eligible_both)} under both`} tone="green" /><Kpi label="Near the line" value={NUM.format(data.near_floor)} sub="within 5% of a floor they missed" tone={data.near_floor ? 'amber' : 'green'} /><Kpi label="Wage / hours floor" value={`${floors.minimum_average_weekly_hours} / ${MONEY.format(floors.minimum_average_weekly_wages_usd)}`} sub={`Tax Year ${floors.tax_year}${floors.lowest_wage_county ? ` · ${floors.lowest_wage_county}` : ''}`} /></div>
      <section className="panel"><h3 className="panel-title">Fiscal window <span className="right">{data.fiscal.assumed ? 'assumed — no rule on file' : 'from the client’s own fiscal rule'}</span></h3><dl className="tcc-kv tcc-kv-wide"><dt>Window</dt><dd>{data.fiscal.begin} → {data.fiscal.end}</dd><dt>Tax year</dt><dd>{data.fiscal.tax_year}</dd><dt>Programme</dt><dd>{data.program_code}</dd></dl>{data.fiscal.convention_matters && <p className="small warn">PILOT-07 — this window spans two calendar years, so the labelling convention changes the answer: by begin it is TY{data.fiscal.tax_year_if_labelled_by_begin}, by end TY{data.fiscal.tax_year_if_labelled_by_end}. Shown as TY{data.fiscal.tax_year} on the regulation’s reading; unconfirmed with the partner.</p>}{data.fiscal.note && <p className="small muted">{data.fiscal.note}</p>}</section>
    </>}
    {showSourceControls && periods && <>
    {/* Rescued from the retired Data Ingestion view. These are not source
        statistics — they are what the Pay Period denominator IS. A cadence
        conflict is a period the engine refused to count, and that refusal
        belongs next to the number it changed rather than on a separate screen
        about ingestion. */}
    <section className="panel"><h3 className="panel-title">Denominator period identity <span className="right">BA-03 · no silent repair</span></h3><div className="tcc-control-grid"><div><span>Source period keys</span><b>{NUM.format(periods.source_period_keys)}</b><small>employee + PPS/PPE/pay date/frequency</small></div><div><span>PPS/PPE periods</span><b>{NUM.format(periods.employee_pps_ppe_periods)}</b><small>denominator identity</small></div><div><span>Records collapsed</span><b>{NUM.format(periods.same_pps_ppe_records_collapsed)}</b><small>lineage retained</small></div><div><span>Cadence conflicts</span><b>{NUM.format(periods.conflicting_frequency_periods)}</b><small>excluded and flagged</small></div></div></section>
    {/* Also rescued: the boundary is a CONSTRAINT on every denominator above.
        Without a leading lookback the first period of the year is short, and a
        short first period is a smaller denominator — which raises an average
        and can make someone look eligible who is not. */}
    <section className={`tcc-invariant ${summary.boundary.boundary_complete ? 'ok' : 'warn'}`}><div><b>Fiscal boundary completeness</b><span>BA-02 / BA-10 · {stageLabel(summary.boundary.status)}</span></div><div><strong>{NUM.format(summary.boundary.prior_ppe_paid_in_fy_rows)}</strong><span>prior PPE paid in FY</span></div><div><strong>{NUM.format(summary.boundary.crossing_start_rows)}</strong><span>crossing-start rows</span></div><div><strong>{NUM.format(summary.boundary.current_ppe_paid_after_fy_rows)}</strong><span>trailing rows excluded</span></div></section>
    {!summary.boundary.boundary_complete && <div className="callout warn"><b>Leading payroll lookback is missing.</b> Earliest valid PPS is {summary.boundary.earliest_valid_pay_period_start}; no rows are synthesized and denominators are not forced to 52 weeks.</div>}
    </>}
    {calculated && <section className="panel"><div className="tcc-panel-toolbar"><div className="tcc-filter-stack"><div className="tabs">{options.map(([id, label]) => <button className={`tab ${status === id ? 'active' : ''}`} key={id} onClick={() => { setStatus(id); setOffset(0); }}>{label}</button>)}</div><button className={`btn btn-secondary ${proximity === 'near_floor' ? 'active' : ''}`} onClick={() => { setProximity(proximity === 'near_floor' ? 'all' : 'near_floor'); setOffset(0); }}>Within 5% of a floor</button></div><label className="tcc-search"><Search size={16} /><input value={query} onChange={(event) => { setQuery(event.target.value); setOffset(0); }} placeholder="Search employee ID…" /></label></div><div className="tcc-table-wrap tcc-table-tall"><table className="tbl tcc-dense-table"><thead><tr>{ELIGIBILITY_HEADS.map(([key, label, cls]) => (key
  ? <SortHeader key={key} label={label} sortKey={key} sort={sort} multi={false} className={cls} onSort={(k) => { setSort((cur) => [{ key: k, desc: cur[0]?.key === k ? !cur[0].desc : false }]); setOffset(0); }} />
  : <th key={label} className={cls}>{label}</th>))}</tr></thead><tbody>{(data?.rows || []).map((row) => <tr key={row.record_token}><td><button className="tcc-link" onClick={() => openEmployee(row.record_token, drillContext)}>{row.employee_id}</button></td><td><Status status={row.status}>{eligibilityLabel(row.status)}</Status></td><td>{row.near_floor ? <span className="pill pill-warn">within 5%</span> : <span className="muted">—</span>}</td><td className="num">{row.totals.hours}</td><td className="num">{MONEY.format(Number(row.totals.wages))}</td><td className="num">{row.min_max.weeks}</td><td className="num">{row.min_max.avg_hours} / {MONEY.format(Number(row.min_max.avg_wages))}</td><td><FlagPair method={row.min_max} /></td><td className="num">{row.pay_period.weeks}</td><td className="num">{row.pay_period.avg_hours} / {MONEY.format(Number(row.pay_period.avg_wages))}</td><td><FlagPair method={row.pay_period} /></td></tr>)}</tbody></table></div>{data && <Pager total={data.total} limit={limit} offset={offset} onChange={setOffset} />}</section>}
  </>;
}

function FlagPair({ method }) { return <div className="tcc-mini-flags"><span className={method.passed_hours ? 'pass' : 'fail'}>H</span><span className={method.passed_wages ? 'pass' : 'fail'}>W</span><span className={method.eligible ? 'pass' : 'fail'}>E</span></div>; }

export function OneZeroView({ openEmployee, scope }) {
  const [method, setMethod] = useState('min_max'); const [data, setData] = useState(null); const [filter, setFilter] = useState(''); const [contributors, setContributors] = useState(null); const [error, setError] = useState(null);
  const clientId = scope?.clientId ?? null; const year = scope?.year ?? null; const jurisdiction = scope?.jurisdiction ?? 'GA';
  const isPortfolio = clientId === PORTFOLIO;
  // Per-client when a client is selected; the sealed certified run otherwise.
  const perClient = !isPortfolio && clientId != null && year != null;
  // Which run should serve the employee drill for these tokens. The sealed
  // service only indexes the certified client-year, so a per-client row that
  // passed no context opened a 404 on every non-certified year.
  const drillContext = perClient
    ? { taxYear: year, state: jurisdiction, accountId: clientId }
    : null;
  useEffect(() => {
    if (isPortfolio) { setData(null); setContributors(null); setError(null); return undefined; }
    let live = true; setData(null); setContributors(null); setError(null);
    const load = perClient
      ? fetchOneZeroMatrix(year, { state: jurisdiction, accountId: clientId, method })
      : fetchWorkspaceOneZero(method);
    load.then((body) => { if (live) setData(body); }).catch((err) => { if (live) setError(err.message); });
    return () => { live = false; };
  }, [method, perClient, year, clientId, jurisdiction]);
  const openContributors = async (row, monthIndex) => {
    if (perClient) {
      // The matrix ships with the response, so the drill-in costs no round trip
      // and cannot disagree with the totals above it.
      const seen = new Map();
      for (const item of data.matrix) {
        if (item.unit_id !== row.unit_id || item.fein !== row.fein || !item.months[monthIndex]) continue;
        seen.set(item.employee_id, { record_token: item.record_token, employee_id: item.employee_id, counted: item.months[monthIndex] });
      }
      setContributors({ method, unit_id: row.unit_id, fein: row.fein, month_index: monthIndex, contributors: [...seen.values()].sort((a, b) => a.employee_id.localeCompare(b.employee_id)) });
      return;
    }
    setContributors(await fetchWorkspaceContributors({ method, unit_id: row.unit_id, fein: row.fein, month_index: monthIndex }));
  };
  const summaryTable = useTableControls(UNIT_SUMMARY_COLUMNS, data?.summary);
  const overlapTable = useTableControls(OVERLAP_COLUMNS, data?.overlap_flags);
  const visibleSummary = summaryTable.rows.filter((row) => `${row.unit_id} ${row.fein}`.toLowerCase().includes(filter.trim().toLowerCase()));
  const overlaps = data?.overlap_flags || [];
  return <>
    <PageHeader eyebrow="What is it worth" title="Monthly employment" sub="Eligible employees allocated to location × legal entity × month (the one/zero matrix), with every overlap disposition visible" />
    <div className="tabs tcc-method-tabs"><button className={`tab ${method === 'min_max' ? 'active' : ''}`} onClick={() => setMethod('min_max')}>Min-Max</button><button className={`tab ${method === 'pay_period' ? 'active' : ''}`} onClick={() => setMethod('pay_period')}>Pay Period</button></div>
    <div className="callout info"><b>{method === 'min_max' ? 'One eligible employee × unit × FEIN span.' : 'One eligible employee × major period × unit × FEIN.'}</b> A month is 1 when the method-specific PPS/PPE range covers its target. Month 12 uses the last PPE when it falls after day 15.</div>
    {isPortfolio ? <div className="callout info">Monthly employment allocates one client’s employees to their units and months. Select a client to see theirs.</div>
      : error ? <div className="callout warn">No monthly employment matrix for this selection: {error}</div>
      : !data ? <div className="panel tcc-loading-inline">Reading the {stageLabel(method)} matrix…</div>
      /* Read from the run that produced it, so a year no run reached carries no
         figure. Zeroes here would say the allocation ran and found nobody. */
      : (perClient && !isCalculated(data)) ? (
        <div className="panel">
          <h2 className="panel-title">Awaiting the next run</h2>
          <p className="page-sub">{data.message}</p>
        </div>
      ) : <>
      <div className="kpi-strip tcc-kpi-4"><Kpi label="Matrix rows" value={NUM.format(data.matrix_rows)} sub="method-specific grain" /><Kpi label="Unit × FEIN rows" value={NUM.format(data.units)} sub="summary grain" tone="accent" />{perClient
        ? <><Kpi label="Contested months" value={NUM.format(data.contested_months)} sub="two units in one month, tie-break applied" tone={data.contested_months ? 'amber' : 'green'} /><Kpi label="Average headcount" value={String(data.annual_average)} sub={`${data.fiscal.begin} → ${data.fiscal.end}`} /></>
        : <><Kpi label="Test of twos" value={NUM.format(overlaps.length)} sub="review required before sign-off" tone={overlaps.length ? 'amber' : 'green'} /><Kpi label="Assumption set" value={String(data.assumption_set_id || '').split('-').pop() || 'OZ'} sub={data.assumption_set_id} /></>}</div>
      <section className="panel"><div className="tcc-panel-toolbar"><h3 className="panel-title">Monthly Average Headcount <span className="right">click a month to inspect contributing employees</span></h3><label className="tcc-search"><Search size={16} /><input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Filter unit or FEIN…" /></label></div><FilterBar {...summaryTable.bar('unit rows')} /><div className="tcc-table-wrap"><table className="tbl tcc-matrix-table"><thead><tr><SortHeader {...summaryTable.head('unit')} /><SortHeader {...summaryTable.head('fein')} />{data.months.map((month) => <th key={month}>{monthLabel(month)}</th>)}<SortHeader {...summaryTable.head('total')} />{perClient ? <SortHeader {...summaryTable.head('average')} /> : <><SortHeader {...summaryTable.head('unrounded')} /><SortHeader {...summaryTable.head('source_rounded')} /><SortHeader {...summaryTable.head('application')} /></>}</tr></thead><tbody>{visibleSummary.map((row) => <tr key={`${row.unit_id}-${row.fein}`}><td className="cell-strong">{row.unit_id}</td><td>{row.fein}</td>{row.month_totals.map((value, index) => <td key={data.months[index]}><button className="tcc-cell-btn" onClick={() => openContributors(row, index)}>{value}</button></td>)}<td>{row.total}</td>{perClient ? <td>{row.average_headcount}</td> : <><td>{row.unrounded_average}</td><td>{row.source_rounded_average}</td><td>{row.application_average}</td></>}</tr>)}</tbody></table></div>{visibleSummary.length === 0 && <p className="tcc-empty">No unit/FEIN rows match this filter.</p>}{!perClient && method === 'pay_period' && data.major_period_controls && <details className="tcc-detail-block"><summary>Major-period classifier controls · OZ-05 proposed</summary><pre>{JSON.stringify(data.major_period_controls, null, 2)}</pre></details>}</section>
      {perClient
        ? <div className="callout info small">The three rounding columns and the per-flag test-of-twos disposition are reconciliation artefacts of the certified run against the partner’s Access output. There is no Access output for this client, so they are not shown rather than shown empty. {data.contested_months} employee-month{data.contested_months === 1 ? ' was' : 's were'} contested and resolved to the most recent unit.</div>
        : overlaps.length > 0 && <section className="panel"><h3 className="panel-title">Test-of-twos review <span className="right">raw candidates → explicit disposition</span></h3><FilterBar {...overlapTable.bar('flags')} /><div className="tcc-table-wrap"><table className="tbl"><thead><tr><SortHeader {...overlapTable.head('employee')} /><SortHeader {...overlapTable.head('month')} /><SortHeader {...overlapTable.head('candidates')} /><SortHeader {...overlapTable.head('kept')} /><SortHeader {...overlapTable.head('basis')} /></tr></thead><tbody>{overlapTable.rows.slice(0, 100).map((flag, index) => <tr key={`${flag.record_token}-${flag.month_index}-${index}`}><td><button className="tcc-link" onClick={() => openEmployee(flag.record_token, drillContext)}>{flag.employee_id}</button></td><td>{flag.month_index + 1}</td><td>{flag.candidate_segment_ids.length}</td><td className="small">{flag.kept_segment_id}</td><td className="small muted">{flag.decision_basis}</td></tr>)}</tbody></table></div></section>}
    </>}
    {contributors && <div className="tcc-contributor-drawer"><div className="tcc-panel-toolbar"><h3>Contributors · month {contributors.month_index + 1}</h3><button className="tcc-icon-btn" onClick={() => setContributors(null)} aria-label="Close contributors">×</button></div><p className="small muted">{contributors.unit_id} · {contributors.fein} · {stageLabel(contributors.method)}</p>{contributors.contributors.length ? contributors.contributors.map((item) => <button key={item.record_token} className="tcc-contributor" onClick={() => openEmployee(item.record_token, drillContext)}><b>{item.employee_id}</b><span>counted {item.counted}</span></button>) : <p>No contributors.</p>}</div>}
  </>;
}

export function CalculationWalkView({ embedded = false } = {}) {
  const [data, setData] = useState(null); useEffect(() => { fetchWorkspaceCalculationWalk().then(setData); }, []);
  return <>{!embedded && <PageHeader eyebrow="Prove it" title="Calculation walk" sub="Source → formula → parameters → intermediate output → assumptions → exceptions → citation" />}{!data ? <div className="panel tcc-loading-inline">Loading the audit trail…</div> : <><section className="panel"><h3 className="panel-title">Reproducibility envelope</h3><dl className="tcc-kv tcc-kv-wide">{Object.entries(data.run_context).map(([key, value]) => <Fragment key={key}><dt>{stageLabel(key)}</dt><dd>{value}</dd></Fragment>)}</dl></section><div className="tcc-walk">{data.steps.map((step, index) => <section className="tcc-walk-step" key={step.step_id}><div className="tcc-walk-index">{String(index + 1).padStart(2, '0')}</div><div><div className="tcc-walk-head"><div><span>{stageLabel(step.stage)} · {stageLabel(step.method)}</span><h3>{step.step_id}</h3></div><span className="pill pill-accent">{step.decision_basis}</span></div><code className="tcc-formula">{step.formula}</code><div className="tcc-walk-grid"><div><b>Inputs</b><pre>{JSON.stringify(step.inputs, null, 2)}</pre></div><div><b>Parameters</b><pre>{JSON.stringify(step.parameters, null, 2)}</pre></div><div><b>Output</b><pre>{JSON.stringify(step.output, null, 2)}</pre></div></div><div className="tcc-walk-meta"><span>Assumptions: {(step.assumption_ids || []).join(', ') || 'none'}</span><span>Exceptions: {(step.exceptions || []).join('; ') || 'none'}</span><span>Source: {step.citation}</span></div><details className="tcc-step-proof"><summary>Reproducibility metadata</summary><dl className="tcc-kv"><dt>Calculation ID</dt><dd>{step.calculation_id}</dd><dt>Code</dt><dd>{step.code_ref}</dd><dt>Source hash</dt><dd>{step.source_hash}</dd><dt>Config hash</dt><dd>{step.config_hash}</dd><dt>Timestamp</dt><dd>{step.timestamp}</dd></dl></details></div></section>)}</div></>}</>;
}

export function CompareView({ openEmployee }) {
  const [data, setData] = useState(null); const [stage, setStage] = useState(null); useEffect(() => { fetchWorkspaceComparison().then(setData); }, []);
  const loadStage = async (name) => { try { setStage(await fetchWorkspaceComparisonStage(name)); } catch { setStage(null); } };
  const stageTable = useTableControls(STAGE_COLUMNS, data?.stage_summaries);
  const diffTable = useTableControls(DIFF_COLUMNS, stage?.differences);
  return <><PageHeader eyebrow="Prove it" title="Back-test" sub="Stage-by-stage reconciliation against the partner’s Access output for the exact same source" />{!data ? <div className="panel tcc-loading-inline">Checking benchmark package…</div> : data.status === 'not_supplied' ? <section className="tcc-awaiting"><FileSearch size={34} /><div><h2>Access outputs not supplied</h2><p>{data.message} No parity claim is made. Our sealed run is ready to compare as soon as the private output package arrives.</p><div className="tcc-chip-row">{data.required_stages.map((item) => <span className="pill pill-neutral" key={item}>{stageLabel(item)}</span>)}</div></div></section> : <><div className={`callout ${data.reconciled ? '' : 'warn'}`}><b>{data.reconciled ? 'All supplied stages reconcile.' : `First divergent stage: ${stageLabel(data.first_divergent_stage)}`}</b></div><section className="panel"><FilterBar {...stageTable.bar('stages')} /><table className="tbl"><thead><tr>{Object.keys(STAGE_COLUMNS).map((key) => <SortHeader key={key} {...stageTable.head(key)} />)}</tr></thead><tbody>{stageTable.rows.map((row) => <tr key={row.stage} onClick={() => loadStage(row.stage)} className="tcc-click-row"><td>{stageLabel(row.stage)}</td><td>{row.benchmark_rows}</td><td>{row.computed_rows}</td><td>{row.exact_rows}</td><td>{row.difference_count}</td><td><Status status={row.reconciled ? 'reconciled' : 'discrepancies'} /></td></tr>)}</tbody></table></section>{stage && <section className="panel"><h3 className="panel-title">{stageLabel(stage.stage)} differences</h3><FilterBar {...diffTable.bar('differences')} /><div className="tcc-table-wrap"><table className="tbl"><thead><tr>{Object.keys(DIFF_COLUMNS).map((key) => <SortHeader key={key} {...diffTable.head(key)} />)}</tr></thead><tbody>{diffTable.rows.slice(0, 500).map((difference, index) => <tr key={index}><td>{difference.record_token ? <button className="tcc-link" onClick={() => openEmployee(difference.record_token)}>{difference.key.join(' · ')}</button> : difference.key?.join(' · ') || '—'}</td><td>{difference.field || 'row'}</td><td>{String(difference.benchmark ?? '—')}</td><td>{String(difference.computed ?? '—')}</td><td>{difference.difference || stageLabel(difference.status)}</td></tr>)}</tbody></table></div></section>}</>}</>;
}

const STAGE_COLUMNS = {
  stage: { key: 'stage', label: 'Stage', type: ENUM, read: (r) => r.stage, format: (v) => stageLabel(v) },
  benchmark: { key: 'benchmark', label: 'Benchmark rows', type: NUMERIC, read: (r) => r.benchmark_rows },
  computed: { key: 'computed', label: 'Computed rows', type: NUMERIC, read: (r) => r.computed_rows },
  exact: { key: 'exact', label: 'Exact rows', type: NUMERIC, read: (r) => r.exact_rows },
  differences: { key: 'differences', label: 'Differences', type: NUMERIC, read: (r) => r.difference_count },
  status: {
    key: 'status', label: 'Status', type: ENUM,
    read: (r) => (r.reconciled ? 'reconciled' : 'discrepancies'), format: (v) => stageLabel(v),
  },
};

const DIFF_COLUMNS = {
  key: { key: 'key', label: 'Key', type: TEXT, read: (d) => (d.key || []).join(' · ') },
  field: { key: 'field', label: 'Field', type: ENUM, read: (d) => d.field || 'row' },
  benchmark: { key: 'benchmark', label: 'Access', type: TEXT, read: (d) => (d.benchmark == null ? '' : String(d.benchmark)) },
  computed: { key: 'computed', label: 'Our run', type: TEXT, read: (d) => (d.computed == null ? '' : String(d.computed)) },
  delta: { key: 'delta', label: 'Δ / status', type: TEXT, read: (d) => d.difference || d.status },
};

export function AssumptionsView() {
  const [data, setData] = useState(null); useEffect(() => { fetchWorkspaceAssumptions().then(setData); }, []);
  return <><PageHeader eyebrow="Prove it" title="Calculations" sub="How each figure is measured — the decisions behind the method, their history, and what would change them" />{!data ? <div className="panel tcc-loading-inline">Loading versioned assumptions…</div> : <><div className="callout info"><b>Tax Year {data.statutory.tax_year} · {data.statutory.minimum_average_weekly_hours} hours · ${data.statutory.minimum_average_weekly_wages_usd} weekly wages.</b> {data.statutory.lowest_wage_county ? `${data.statutory.lowest_wage_county} County, ` : ''}DOL report year {data.statutory.dol_report_year ?? 'n/a'}. Resolved from <code>{data.statutory.source}</code>{data.statutory.prototype_verify ? ' — UNVERIFIED placeholder' : ''}. Active set {data.step1.assumption_set_id}.</div><div className="tcc-history-strip">{Object.entries(data.history).flatMap(([method, rows]) => rows.map((row) => <div key={row.assumption_set_id}><span>{stageLabel(method)} history</span><b>{row.assumption_set_id}</b><code>{shortHash(row.sha256, 16)}</code></div>))}</div><div className="tcc-assumption-columns">{[['step1', 'Step 1 eligibility'], ['onezero', 'Monthly employment']].map(([key, label]) => { const group = data[key]; return <section className="panel" key={key}><h3 className="panel-title">{label}<Status status={group.status}>{stageLabel(group.status)}</Status></h3><p className="small muted">{group.assumption_set_id} · {shortHash(group.sha256, 16)} · supersedes {group.supersedes}</p><details className="tcc-detail-block"><summary>Evidence basis and change control</summary><p className="small">{group.source_basis.join(' · ')}</p><p className="small"><b>Supersession:</b> {group.change_control.supersession_rule}</p></details><div className="tcc-assumption-list">{assumptionEntries(group).map((item) => <article key={item.id}><div><b>{item.id}</b><Status status={item.status}>{stageLabel(item.status)}</Status></div><p>{item.decision}</p><small><b>Revisit when:</b> {item.falsified_by}</small></article>)}</div></section>; })}</div></>}</>;
}
