// Stage 1 — Data Ingestion. The agent-automated ingest surface, postured for
// human validation/correction: raw BCS rows → canonical transform → QC
// exceptions, with the granular source→output detail on screen and accept/drop/
// flag controls on every anomaly (nothing is silently dropped). Self-fetching.
import { useCallback, useEffect, useState } from 'react';
import { fetchIngestion, resolveException, fetchIngestionRows, hasYear } from '../api.js';
import PageHeader from './PageHeader.jsx';
import SortHeader from './SortHeader.jsx';
import { FilterBar } from './ColumnFilter.jsx';
import useTableControls from './useTableControls.js';
import { ENUM, NUMERIC, TEXT } from '../lib/gridFilter.js';

const NUM = new Intl.NumberFormat('en-US');
const PAGE = 25;

const exceptionStatus = (x) => {
  const res = x.resolution;
  if (!res) return 'open';
  return res.resolution === 'assign' ? 'kept' : res.resolution;
};

const EXCEPTION_COLUMNS = {
  type: {
    key: 'type', label: 'Type', type: ENUM, read: (x) => x.type,
    format: (v) => (v === 'test_of_twos' ? 'double-count' : 'scraggly period'),
  },
  employee: { key: 'employee', label: 'Employee', type: TEXT, read: (x) => x.employee_id },
  detail: {
    key: 'detail', label: 'Detail', type: TEXT,
    read: (x) => (x.type === 'test_of_twos' ? `${x.month} ${(x.units || []).map((u) => u.worksite_name).join(' ')}` : `${x.pay_date}`),
  },
  status: { key: 'status', label: 'Status', type: ENUM, read: exceptionStatus },
};

const FIELD_COLUMNS = {
  source: { key: 'source', label: 'Source column', type: TEXT, read: (f) => f.source },
  canonical: { key: 'canonical', label: 'Canonical field', type: TEXT, read: (f) => f.canonical },
  note: { key: 'note', label: 'Why', type: TEXT, read: (f) => f.note },
};

const PAY_CODE_COLUMNS = {
  pay_code: { key: 'pay_code', label: 'Pay code', type: ENUM, read: (p) => p.pay_code },
  count: { key: 'count', label: 'Rows', type: NUMERIC, read: (p) => p.count },
};

/** The source browser's columns, sorted by the SERVER (see `ingestion_rows`). */
const ROW_SORTS = [
  ['employee', 'Employee'], ['worksite', 'Worksite'], ['fein', 'FEIN'],
  ['pps', 'PP start'], ['ppe', 'PP end'], ['pay_date', 'Pay date'], ['tax_year', 'Tax_Year'],
  ['hours', 'Hours', 'num'], ['wages', 'Wages', 'num'], ['pay_code', 'Pay code'],
];

export default function DataIngestionView({ taxYear = 2025, accountId = null, canResolve = false, reloadKey = 0, onResolved }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  // Full-source browser (read-only, searchable, paged). Sorted SERVER-side:
  // it is one page of the whole payroll, and sorting only the page on screen
  // would present 25 rows as the top of a list they are not the top of.
  const [rowsData, setRowsData] = useState(null);
  const [rowQuery, setRowQuery] = useState('');
  const [rowOffset, setRowOffset] = useState(0);
  const [rowSort, setRowSort] = useState([{ key: 'employee', desc: false }]);

  // The small tables sort and filter in the browser (29 Sep: every table).
  const exceptionTable = useTableControls(EXCEPTION_COLUMNS, data?.qc?.exceptions);
  const fieldTable = useTableControls(FIELD_COLUMNS, data?.field_map);
  const payCodeTable = useTableControls(PAY_CODE_COLUMNS, data?.pay_code_split);

  // The scope resolves a year asynchronously, and reports `null` until it does.
  // A default parameter does not cover that — `taxYear = 2025` only fires for
  // `undefined` — so this has to be an explicit check, not a fallback.
  const ready = hasYear(taxYear);

  const load = useCallback(() => {
    if (!ready) return;
    setBusy(true);
    fetchIngestion(taxYear, 'GA', accountId)
      .then((d) => { setData(d); setError(null); })
      .catch((e) => setError(String(e)))
      .finally(() => setBusy(false));
  }, [taxYear, accountId, reloadKey, ready]);

  useEffect(() => { load(); }, [load]);

  // Debounced source-browser fetch on query / page change.
  useEffect(() => {
    if (!ready) return undefined;
    const t = setTimeout(() => {
      fetchIngestionRows(taxYear, {
        q: rowQuery, limit: PAGE, offset: rowOffset, state: 'GA', accountId,
        sort: rowSort[0]?.key, order: rowSort[0]?.desc ? 'desc' : 'asc',
      })
        .then(setRowsData)
        .catch(() => setRowsData(null));
    }, 250);
    return () => clearTimeout(t);
  }, [taxYear, accountId, rowQuery, rowOffset, rowSort, ready]);

  const resolve = async (exceptionId, payload) => {
    try {
      await resolveException(taxYear, exceptionId, { reviewer: 'Reviewer', ...payload });
      load();
      onResolved?.(); // recompute Headcount / Overview off the corrected rows
    } catch (e) { setError(String(e)); }
  };

  const header = (
    <PageHeader
      eyebrow="What needs a decision"
      title="Payroll data"
      sub="How the source payroll becomes the calculation input, and the exceptions that need a reviewer"
    />
  );

  if (!ready) {
    return <>{header}<section className="panel"><p className="small muted">Resolving which tax year to read…</p></section></>;
  }
  if (error) {
    return <>{header}<section className="panel"><p className="small muted">Unavailable: {error}</p></section></>;
  }
  if (!data) {
    return <>{header}<section className="panel"><p className="small muted">Loading the payroll pipeline…</p></section></>;
  }

  const t = data.totals;
  const qc = data.qc;
  const exceptions = qc.exceptions || [];

  return (
    <>
      {header}
      <div className="callout info">
        <b>Ingestion is agent-automated — you validate the exceptions.</b>{' '}
        The <b>{(data.automation?.agents || []).join(' + ')}</b> ingest payroll continuously; the numbers below are
        deterministic. This page shows <b>how the source becomes the output</b> — raw rows → canonical records →
        QC — so a reviewer can confirm the transform and resolve anomalies. The agent never drops a record.
      </div>

      <div className="kpi-strip kpi-strip-4">
        <div className="kpi-card"><div className="kpi-label">Employees</div><div className="kpi-value">{NUM.format(t.distinct_employees)}</div><div className="kpi-sub">Georgia · fiscal {taxYear}</div></div>
        <div className="kpi-card"><div className="kpi-label">Worksites</div><div className="kpi-value">{NUM.format(t.distinct_worksites)}</div><div className="kpi-sub">unit granularity</div></div>
        <div className="kpi-card"><div className="kpi-label">Includable wage rows</div><div className="kpi-value">{NUM.format(t.includable_rows)}</div><div className="kpi-sub">cash-basis by pay date</div></div>
        <div className={`kpi-card ${qc.summary.unresolved > 0 ? 'amber' : 'green'}`}><div className="kpi-label">QC exceptions</div><div className="kpi-value">{qc.summary.total_anomalies}</div><div className="kpi-sub">{qc.summary.unresolved} unresolved</div></div>
      </div>

      {/* 1) Transform pipeline — how the source becomes the output. */}
      <section className="panel">
        <h3 className="panel-title">Payroll pipeline <span className="right small muted">source → canonical → QC · deterministic</span></h3>
        <div className="ingest-flow">
          {data.pipeline.map((s, i) => {
            const unchanged = i > 0 && s.count === data.pipeline[i - 1].count;
            return (
              <div className="ingest-stage" key={s.stage}>
                <div className="ingest-stage-count">{NUM.format(s.count)}</div>
                <div className="ingest-stage-name">{s.stage}</div>
                <div className="ingest-stage-note small muted">{s.note}{unchanged ? ' · unchanged on this data' : ''}</div>
                {i < data.pipeline.length - 1 && <div className="ingest-arrow">→</div>}
              </div>
            );
          })}
        </div>
      </section>

      {/* 2) QC exception report — the validation checkpoint (the human-in-the-loop moment). */}
      <section className="panel">
        <h3 className="panel-title">
          QC exception report
          <span className="right small muted">
            test-of-twos (CALC-07) + scraggly pay periods (CALC-08) · {qc.summary.unresolved} unresolved
          </span>
        </h3>
        <p className="small muted u-mt-0">
          The human-in-the-loop checkpoint — the partner's two by-eye checks, automated. Nothing is dropped silently.
          <b> Resolving actually flows into the calculation</b> — for a double-count you pick which unit owns the
          head that month, and the engine reassigns it, so Headcount and the per-employee drill recompute.
        </p>
        {exceptions.length === 0 ? (
          <div className="callout u-mt-1">
            <b>Clean.</b> No double-counts and no trivial-value pay periods in {taxYear} — the synthetic GA feed
            passes automated QC. On a real feed, anomalies would list here for accept / drop / flag.
          </div>
        ) : (
          <>
          <FilterBar {...exceptionTable.bar('exceptions')} />
          <table className="tbl">
            <thead>
              <tr>
                <SortHeader {...exceptionTable.head('type')} />
                <SortHeader {...exceptionTable.head('employee')} />
                <SortHeader {...exceptionTable.head('detail')} />
                <SortHeader {...exceptionTable.head('status')} />
                <th>Resolve</th>
              </tr>
            </thead>
            <tbody>
              {exceptionTable.rows.map((x) => {
                const res = x.resolution;
                const keptName = res && res.resolution === 'assign'
                  ? ((x.units || []).find((u) => u.worksite_id === res.keep_worksite)?.worksite_name || res.keep_worksite)
                  : null;
                const statusLabel = !res
                  ? 'open'
                  : res.resolution === 'assign'
                    ? `kept ${keptName}`
                    : res.resolution;
                return (
                  <tr key={x.exception_id}>
                    <td><span className="pill pill-warn">{x.type === 'test_of_twos' ? 'double-count' : 'scraggly period'}</span></td>
                    <td className="cell-strong">{x.employee_id}</td>
                    <td className="small muted">
                      {x.type === 'test_of_twos'
                        ? `${x.month} · counted at ${x.unit_count} units: ${(x.units || []).map((u) => `${u.worksite_name} (${u.hours}h)`).join(' vs ')}`
                        : `${x.pay_date} · ${x.hours} hrs · $${x.wages}`}
                    </td>
                    <td><span className={`pill ${res ? 'pill-ok' : 'pill-neutral'}`}>{statusLabel}</span></td>
                    <td>
                      {res ? (
                        <button className="row-action" disabled={!canResolve} onClick={() => resolve(x.exception_id, { resolution: 'reopen' })}>Reopen</button>
                      ) : (
                        <select
                          className="qc-resolve-select"
                          disabled={!canResolve}
                          defaultValue=""
                          onChange={(e) => {
                            const v = e.target.value;
                            if (!v) return;
                            if (v.startsWith('assign:')) resolve(x.exception_id, { resolution: 'assign', keep_worksite: v.slice(7) });
                            else resolve(x.exception_id, { resolution: v });
                            e.target.value = '';
                          }}
                        >
                          <option value="">Resolve…</option>
                          {x.type === 'test_of_twos' ? (
                            <>
                              {(x.units || []).map((u) => (
                                <option key={u.worksite_id} value={`assign:${u.worksite_id}`}>
                                  Keep {u.worksite_name} ({u.hours}h)
                                </option>
                              ))}
                              <option value="accept">Accept as-is (count both)</option>
                            </>
                          ) : (
                            <>
                              <option value="accept">Accept (count it)</option>
                              <option value="drop">Drop the period</option>
                            </>
                          )}
                        </select>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          </>
        )}
        {!canResolve && exceptions.length > 0 && (
          <p className="small muted u-mt-2">Your role can view exceptions but not resolve them.</p>
        )}
      </section>

      {/* 3) Full source browser — read-only, searchable, paged (the granular input). */}
      <section className="panel">
        <h3 className="panel-title">
          Source rows
          <span className="right small muted">read-only · searchable · {rowsData ? NUM.format(rowsData.total) : '…'} GA rows in fiscal {taxYear}</span>
        </h3>
        <div className="toolbar-right u-mb-3">
          <input
            type="search"
            className="toolbar-input"
            placeholder="Search employee / worksite / date / pay code…"
            value={rowQuery}
            onChange={(e) => { setRowQuery(e.target.value); setRowOffset(0); }}
          />
        </div>
        <div className="u-scroll-x">
          <table className="tbl">
            <thead>
              <tr>
                {ROW_SORTS.map(([key, label, cls]) => (
                  <SortHeader
                    key={key}
                    label={label}
                    sortKey={key}
                    sort={rowSort}
                    multi={false}
                    className={cls}
                    onSort={(k) => {
                      setRowSort((cur) => [{ key: k, desc: cur[0]?.key === k ? !cur[0].desc : false }]);
                      setRowOffset(0);
                    }}
                  />
                ))}
              </tr>
            </thead>
            <tbody>
              {(rowsData?.rows || []).map((r, i) => (
                <tr key={`${r.Employee_ID}-${r.Pay_Date}-${i}`}>
                  <td className="cell-strong">{r.Employee_ID}</td>
                  <td className="cell-sub" title={r.Worksite_ID}>{r.Worksite_Name || r.Worksite_ID}</td>
                  <td className="small muted">{r.Entity_FEIN}</td>
                  <td className="small">{r.Pay_Period_Start}</td>
                  <td className="small">{r.Pay_Period_End}</td>
                  <td className="small">{r.Pay_Date}</td>
                  <td className="small">{r.Tax_Year}</td>
                  <td className="num">{r.Hours_Worked}</td>
                  <td className="num">{r.Gross_Wages}</td>
                  <td>{r.Pay_Code}</td>
                </tr>
              ))}
              {rowsData && rowsData.rows.length === 0 && (
                <tr><td colSpan={10} className="small muted u-empty-cell">No rows match “{rowQuery}”.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        {rowsData && rowsData.total > PAGE && (
          <div className="row-action-group row-action-inline">
            <button className="btn btn-secondary" disabled={rowOffset === 0} onClick={() => setRowOffset(Math.max(0, rowOffset - PAGE))}>Prev</button>
            <span className="small muted">Rows {rowOffset + 1}–{Math.min(rowOffset + PAGE, rowsData.total)} of {NUM.format(rowsData.total)}</span>
            <button className="btn btn-secondary" disabled={rowOffset + PAGE >= rowsData.total} onClick={() => setRowOffset(rowOffset + PAGE)}>Next</button>
          </div>
        )}
        <p className="small muted u-mt-2">
          Note <b>Tax_Year</b> vs <b>Pay_Date</b> — rows count in the year they were PAID (cash-basis, DATA-06). Read-only evidence.
        </p>
      </section>

      {/* 4) Transform rules — reference detail (collapsed). */}
      <details className="panel oz-detail">
        <summary className="panel-title u-clickable">
          Transform rules <span className="right small muted">field map + pay-code classification</span>
        </summary>
        <div className="grid-2 u-mt-4">
          <div>
            <div className="panel-subtitle u-mb-1">Source → canonical field map (DATA-03)</div>
            <FilterBar {...fieldTable.bar('fields')} />
            <table className="tbl">
              <thead>
                <tr>
                  <SortHeader {...fieldTable.head('source')} />
                  <SortHeader {...fieldTable.head('canonical')} />
                  <SortHeader {...fieldTable.head('note')} />
                </tr>
              </thead>
              <tbody>
                {fieldTable.rows.map((f) => (
                  <tr key={f.source}>
                    <td className="cell-strong">{f.source}</td>
                    <td className="cell-sub">{f.canonical}</td>
                    <td className="small muted">{f.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div>
            <div className="panel-subtitle u-mb-1">Pay-code classification <span className="right small muted">wage-basis · GA = all remuneration</span></div>
            <FilterBar {...payCodeTable.bar('pay codes')} />
            <table className="tbl">
              <thead>
                <tr>
                  <SortHeader {...payCodeTable.head('pay_code')} />
                  <SortHeader {...payCodeTable.head('count')} className="num" />
                </tr>
              </thead>
              <tbody>
                {payCodeTable.rows.map((p) => (
                  <tr key={p.pay_code}><td className="cell-strong">{p.pay_code}</td><td className="num">{NUM.format(p.count)}</td></tr>
                ))}
              </tbody>
            </table>
            <p className="small muted u-mt-2">
              {NUM.format(t.excluded_rows)} non-wage lines (mileage / reimbursement) suppressed from the wage base;
              hours/wages retained per the ingested rule config. The synthetic feed is Regular + Overtime only, so
              this filter is a no-op here — proven on a dedicated fixture.
            </p>
          </div>
        </div>
      </details>
    </>
  );
}
