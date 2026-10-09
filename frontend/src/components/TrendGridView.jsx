import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  AlertTriangle, ChevronDown, ChevronRight, Loader2, TrendingUp, X,
} from 'lucide-react';
import {
  fetchClientUnit, fetchClientUnits, fetchUnitRebase, isCalculated, runClientCalculation, saveBaseYear,
} from '../api.js';
import { PORTFOLIO, placeholderYears } from '../lib/scopeDimension.js';
import { USD, money } from '../lib/coverage.js';
import { NUM } from '../lib/reference.js';
import { trendFromGold } from '../lib/goldTrend.js';
import InsightBar, { provenanceLine } from './InsightBar.jsx';
import MethodTabs from './MethodTabs.jsx';
import { filterBlocks, formatSort, parseSort, sortRows, toggleSort } from '../lib/gridSort.js';
import { isWhatIfTarget, whatIfLink } from '../lib/whatIf.js';
import {
  ENUM, NUMERIC, TEXT, YEAR, applyFilters, formatFilters, parseFilters, presentValues,
} from '../lib/gridFilter.js';
import { ColumnFilter, FilterBar } from './ColumnFilter.jsx';
import SortHeader from './SortHeader.jsx';
import useTableControls from './useTableControls.js';
import {
  MONTH_LABELS, buildBlocks, fmtHeadcount, monthTone, pillClass, rowTone,
  readingMeta, summariseTrend, trendState, unreachableFor,
} from '../lib/trendGrid.js';
import {
  baseYearChoices, designationCode, designationTitle, formatRebase, parseRebase, rebaseBlock,
} from '../lib/trendGrid.js';

/**
 * The year rows this grid can filter, one control per column TYPE.
 *
 * 36 rows is not a query, so this is all client-side — the opposite call from
 * the unit grid, which pushes the identical grammar into SQL because 10,236
 * employees do not survive a round trip.
 *
 * `Reading` offers the statuses PRESENT in the data rather than a hardcoded
 * list: a hardcoded one goes stale the first time a status is renamed and then
 * offers a filter that matches nothing, which reads as "no rows" rather than
 * "no such value".
 */
export const ROW_COLUMNS = {
  tax_year: {
    key: 'tax_year', label: 'Tax year', type: YEAR, read: (row) => row.tax_year,
    format: (value) => `TY${value}`,
  },
  designation: {
    key: 'designation', label: 'Designation', type: ENUM, read: (row) => designationCode(row),
  },
  total: { key: 'total', label: 'TOT', type: NUMERIC, read: (row) => row.total },
  average_headcount: {
    key: 'average_headcount', label: 'AVG', type: NUMERIC, read: (row) => row.average_headcount,
  },
  status: {
    key: 'status', label: 'Reading', type: ENUM, read: (row) => row.status,
    format: (value) => String(value).replace(/_/g, ' '),
  },
  net_new_vs_base: {
    key: 'net_new_vs_base', label: 'Net new', type: NUMERIC, read: (row) => row.net_new_vs_base,
  },
};

/** The location text filter, as a chip so the count statement can include it. */
const UNIT_COLUMN = { key: 'unit', label: 'Location', type: TEXT, read: (block) => block.unit_id };

/**
 * The trend grid — every location, every year, in one screen.
 *
 * This is the shape the partner already reads the credit in: a block per filing
 * location, a row per tax year, twelve monthly headcount columns, and the credit
 * stream the location's base year opened. The portal previously made an operator
 * assemble that picture from four separate views and remember which one followed
 * the client selector, which is a learning curve rather than a product.
 *
 * Three things it is careful about:
 *
 * - **Nothing here is a calculation.** Every figure is READ from `tcc_gold`
 *   through `GET /api/v2/clients/{id}/units`, including the sums — the roll-up
 *   strip renders `SUM(annual_credit_usd)` as SQL computed it rather than
 *   re-adding the rows on screen. A page load runs no engine.
 * - **"Not calculated" is rendered as itself.** A client with no successful run
 *   gets the statement and a Run button, never an empty grid or a $0. Those say
 *   something false about the client's payroll.
 * - **The base year and the tier are both unconfirmed.** They change whether a
 *   year qualifies, so they are banner-flagged rather than footnoted.
 */

function Kpi({ label, value, sub, tone }) {
  return (
    <div className={`kpi-card${tone ? ` ${tone}` : ''}`}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {sub ? <div className="kpi-sub">{sub}</div> : null}
    </div>
  );
}

function TierPill({ row }) {
  const code = designationCode(row);
  if (code === 'Unassigned') {
    return <span className="pill pill-neutral" title={designationTitle(row)}>Unassigned</span>;
  }
  return <span className="pill pill-accent" title={designationTitle(row)}>{code}</span>;
}

/**
 * Designation is a property of the LOCATION-YEAR. The partner reads it down the
 * column — "T1, T1, T1B40, T1" — because the year a location was bottom-40 is
 * the year its jobs could be created, even when today's tier would not allow
 * it. So every row carries its own, immediately right of the tax year.
 *
 * The header keeps a summary: the one code when the years agree, "varies"
 * when they do not. `tier_source: unassigned` is a real statement — no
 * designation is on record — so it is shown, not dropped.
 */
function tierOfBlock(block) {
  const keys = new Set(block.rows.map((row) => designationCode(row)));
  return { varies: keys.size > 1, row: block.rows[0] };
}

/** One tax-year row: designation, twelve months, total, average, and the verdict. */
function YearRow({ row, block, unreachable, onOpenMonth, onOpenYear, onWhatIf }) {
  const meta = readingMeta(row);
  // An open year: months past its closed ones have not happened yet.
  const open = row.status === 'in_progress';
  const closedMonths = open ? Number(row.months_reachable || 0) : 12;
  // The Reading is also the way into What-if for this location-year. A base
  // year IS the baseline and a partial year has no full measurement to move,
  // so both stay statements rather than controls.
  const actionable = !!onWhatIf && isWhatIfTarget(row);
  // A year before the base: from a preview, or written by a run from a saved base.
  const beforeBase = row.before_base || row.status === 'before_base';
  return (
    <tr className={`trend-year trend-${rowTone(row)}${beforeBase ? ' trend-before-base' : ''}`}>
      <th scope="row" className="trend-rowhead">
        <button className="tcc-link" onClick={() => onOpenYear(block, row)}>
          TY{row.tax_year}
        </button>
      </th>
      <td className="trend-tier"><TierPill row={row} /></td>
      {row.month_totals.map((value, index) => {
        const notYet = open && index >= closedMonths && !value;
        // Nothing spans this month's measuring date. With a count, the Month-12
        // rule counted it and it reads like any month (the title still says
        // how); with none, it is hatched so a calendar zero is not read as a
        // location that emptied out.
        const offCalendar = !notYet && unreachable.has(index);
        const unreached = offCalendar && !value;
        return (
          <td
            key={MONTH_LABELS[index]}
            className={`trend-cell trend-${beforeBase ? 'muted' : monthTone(value, {
              baseMonthlyAverage: block.baseMonthlyAverage,
              // That year's statute: the minimum is base + the year's threshold.
              threshold: row.threshold ?? block.rows.find((r) => r.threshold != null)?.threshold,
              isBaseYear: row.is_base_year,
              unreachable: offCalendar,
            })}${unreached ? ' trend-unreached' : ''}${notYet ? ' trend-not-yet' : ''}`}
          >
            <button
              className="tcc-cell-btn"
              title={notYet
                ? `${MONTH_LABELS[index]} ${row.tax_year} · not yet — TY${row.tax_year} is still open`
                : offCalendar
                ? (value
                  // Month 12 retargets to the employee's last pay-period end when
                  // it falls after the 15th. That is the only way a month nothing
                  // spans still produces a count.
                  ? `${MONTH_LABELS[index]} ${row.tax_year} · ${fmtHeadcount(value)} counted on each employee's last pay-period end (Month-12 rule) — no period spans the month end`
                  : `${MONTH_LABELS[index]} ${row.tax_year} · no pay period reaches this month's measuring date, and no period ended after the 15th for the Month-12 rule to use`)
                : `${MONTH_LABELS[index]} ${row.tax_year} · ${fmtHeadcount(value)} counted`}
              onClick={() => onOpenMonth(block, row, index)}
            >
              {unreached && !value ? '·' : fmtHeadcount(value)}
            </button>
          </td>
        );
      })}
      <td className="num trend-total">{fmtHeadcount(row.total)}</td>
      <td
        className="num trend-avg"
        title={open ? `Average over the ${closedMonths} closed months, not twelve — the rest of TY${row.tax_year} has not happened` : undefined}
      >
        {row.average_headcount.toFixed(1)}{open ? <sup>{closedMonths}m</sup> : null}
      </td>
      <td className="trend-verdict">
        {actionable ? (
          <button
            type="button"
            className={`pill pill-action ${pillClass(meta.tone)}`}
            title={row.status === 'below_minimum' || (open && !row.qualified)
              ? `${meta.hint} Open What-if for ${block.unit_id} TY${row.tax_year}, pre-filled with what it would take.`
              : `${meta.hint} Open What-if for ${block.unit_id} TY${row.tax_year}.`}
            aria-label={`${meta.label}: open What-if for ${block.unit_id} TY${row.tax_year}`}
            onClick={() => onWhatIf(block, row)}
          >
            {meta.label}
          </button>
        ) : (
          <span className={`pill ${pillClass(meta.tone)}`} title={meta.hint}>{meta.label}</span>
        )}
        {row.backfilled ? <span className="pill pill-ok" title="Re-qualified after a year below the minimum">Backfill</span> : null}
        {/* The partner: "year one, year two, year three". Counted from the chosen base. */}
        {row.year_number ? <span className="trend-year-number" title={`Year ${row.year_number} from the chosen base`}>YR{row.year_number}</span> : null}
      </td>
      <td className="num trend-netnew">{row.is_base_year || beforeBase ? '—' : row.net_new_vs_base.toFixed(1)}</td>
    </tr>
  );
}

/**
 * One location, as a ROW rather than a card.
 *
 * The card cost roughly 400px before the first data row and repeated per unit,
 * so a twenty-location client spent its whole viewport on chrome. Weight and a
 * hairline rule carry the separation instead.
 *
 * Two things survive the collapse and are not decoration:
 *
 * - The tranche chips are the claimable-per-year projection INCLUDING future
 *   years, a different grain from the unit-year rows, so they cannot fold into
 *   a column on one. They move into the expanded detail, keeping the dashed,
 *   dimmed treatment that separates a forecast from a measured installment.
 * - `block.sentence` is the plainest summary on the page. It moves with them.
 */
function UnitBlock({
  block, expanded, detail, unreachableBy, sort, onSort, onToggle, onToggleDetail,
  filters, onFilter, statusOptions, yearOptions, designationOptions,
  onOpenMonth, onOpenYear, onWhatIf, baseChoices = [], inferredBaseYear, onRebase, rebaseState,
  onSaveBase, saveState,
}) {
  const tier = tierOfBlock(block);
  const chosenBase = block.rebased?.base_year ?? inferredBaseYear;
  // The run's base came from a saved choice rather than being inferred.
  const savedBase = (block.baseRow || block.rows.find((r) => r.is_base_year))?.base_year_source === 'override';
  const [reason, setReason] = useState('');
  const latest = block.latest;
  const latestMeta = latest ? readingMeta(latest) : null;
  return (
    <div className={`trend-block${block.attention ? ' attention' : ''}`}>
      <div className="trend-unit-row">
        <button
          className="trend-block-toggle"
          onClick={() => onToggle(block.unit_id)}
          aria-expanded={expanded}
          title={expanded ? 'Hide years' : 'Show years'}
        >
          {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </button>

        <span className="trend-unit-name">
          {block.attention ? <AlertTriangle size={13} className="trend-unit-flag" /> : null}
          {block.name}
        </span>
        <code className="trend-unit-id">{block.unit_id}</code>
        <span className="trend-unit-fein">{block.feins.join(' · ') || '—'}</span>
        <span className="trend-unit-tier">
          {tier.varies
            ? <span className="pill pill-neutral" title="Designation changes across these years">Designation varies</span>
            : <TierPill row={tier.row} />}
        </span>
        {/* WI-21. Which year this location is measured from. The run inferred
            one; choosing another re-prices the view, and saves nothing. */}
        {onRebase && baseChoices.length > 1 ? (
          <label className={`trend-base-picker${block.rebased ? ' active' : ''}`}>
            <span>Base</span>
            <select
              value={chosenBase ?? ''}
              onChange={(event) => onRebase(block.unit_id, Number(event.target.value))}
              aria-label={`Base year for ${block.unit_id}`}
            >
              {baseChoices.map((year) => (
                <option key={year} value={year}>
                  TY{year}{year === inferredBaseYear ? (savedBase ? ' (saved)' : ' (run)') : ''}
                </option>
              ))}
            </select>
          </label>
        ) : <span aria-hidden="true" />}

        {/* The two figures that decide something. Colour only where it encodes
            state, and a base year is NOT a below-minimum year: one means we
            hold no prior year, the other that they did not grow. */}
        <span className="trend-unit-figure">
          <span className="trend-unit-cap">Net new</span>
          <b className={latest && !latest.is_base_year ? `trend-${rowTone(latest)}-text` : ''}>
            {latest ? (latest.is_base_year ? '—' : latest.net_new_vs_base.toFixed(1)) : '—'}
          </b>
        </span>
        <span className="trend-unit-figure">
          <span className="trend-unit-cap">Credit</span>
          <b>{block.total_annual_credit_usd ? money(block.total_annual_credit_usd) : '—'}</b>
        </span>
        {latestMeta ? (
          <span className={`pill ${pillClass(latestMeta.tone)}`} title={latestMeta.hint}>
            {latestMeta.label}
          </span>
        ) : null}
        {/* Separate from the years toggle. The tranche stream is a different
            grain and costs real height, so it must not be the price of seeing
            the table. */}
        <button
          type="button"
          className="trend-unit-more"
          aria-expanded={detail}
          onClick={() => onToggleDetail(block.unit_id)}
          title="Claimable per year, and the plain-English reading"
        >
          {detail ? 'Less' : 'Detail'}
        </button>
      </div>

      {block.rebased ? (
        <div className="callout info trend-rebased" role="status">
          <b>Base year set to TY{block.rebased.base_year}</b> — the run measured this location
          from TY{block.rebased.inferred_base_year}. Re-priced here from the run&apos;s own
          averages: <b>not saved</b>, not the certified figures, and not in the totals above.
          {' '}Credit {block.rebased.delta_annual_credit_usd >= 0 ? '+' : '−'}
          {money(Math.abs(block.rebased.delta_annual_credit_usd))} against the run.{' '}
          <button type="button" className="tcc-link" onClick={() => onRebase?.(block.unit_id, inferredBaseYear)}>
            Back to TY{block.rebased.inferred_base_year}
          </button>
          {onSaveBase ? (
            <span className="trend-save-base">
              <input
                type="text"
                value={reason}
                maxLength={2000}
                placeholder="Why (recorded with the change)"
                aria-label={`Reason for saving TY${block.rebased.base_year} as ${block.unit_id}'s base year`}
                onChange={(event) => setReason(event.target.value)}
              />
              <button
                type="button"
                className="btn btn-primary"
                disabled={saveState?.saving || saveState?.recalculating}
                onClick={() => onSaveBase(block.unit_id, block.rebased.base_year, reason.trim() || null)}
              >
                {saveState?.saving ? 'Saving…' : `Save TY${block.rebased.base_year} as the base year`}
              </button>
            </span>
          ) : null}
        </div>
      ) : null}
      {savedBase && !block.rebased && onSaveBase ? (
        <p className="small muted trend-saved-base">
          Base year TY{inferredBaseYear} was <b>saved</b> for this location — every figure below is
          measured from it. The run it replaced is kept as history.{' '}
          <button
            type="button"
            className="tcc-link"
            disabled={saveState?.saving || saveState?.recalculating}
            onClick={() => onSaveBase(block.unit_id, null, null)}
          >
            Clear the saved base year
          </button>
        </p>
      ) : null}
      {saveState?.recalculating ? (
        <div className="callout info" role="status">
          <Loader2 size={14} className="spin" /> {saveState.year == null
            ? 'Cleared. Recalculating with the run choosing its own base'
            : `Saved. Recalculating ${block.unit_id} from TY${saveState.year}`}
          {' '}— this takes a few minutes, and the grid updates when the new run lands.
          The Targeting book is unaffected: it measures each year against the one before.
        </div>
      ) : null}
      {saveState?.error ? <div className="callout warn">{saveState.error}</div> : null}
      {rebaseState?.error ? <div className="callout warn">{rebaseState.error}</div> : null}
      {rebaseState?.loading ? <div className="callout info"><Loader2 size={14} className="spin" /> Re-pricing against TY{rebaseState.year}…</div> : null}

      {detail && (
        <div className="trend-unit-detail">
          <p className="trend-block-note">
            {block.attention ? <AlertTriangle size={13} /> : null}
            {block.sentence}
          </p>
          <div className="trend-block-credits">
            {block.credits.map((column) => (
              <div
                key={column.label}
                className={`trend-credit${column.projected ? ' projected' : ''}`}
                title={column.projected
                  ? `TY${column.tax_year} · projected, not a measured installment`
                  : `TY${column.tax_year} · measured installment`}
              >
                <span className="trend-credit-label">{column.label}</span>
                <span className="trend-credit-value">
                  {column.claimable_usd ? money(column.claimable_usd) : '—'}
                </span>
                <span className="trend-credit-year">
                  TY{column.tax_year}{column.projected ? ' · projected' : ''}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {expanded && (
        <div className="tbl-scroll trend-scroll">
          <table className="tbl tbl-compact trend-table">
            <thead>
              <tr>
                <SortHeader label="Tax year" sortKey="tax_year" sort={sort} onSort={onSort} className="trend-corner" spec={ROW_COLUMNS.tax_year} filters={filters} onFilter={onFilter} options={yearOptions} />
                <SortHeader label="Designation" sortKey="designation" sort={sort} onSort={onSort} className="trend-tier" spec={ROW_COLUMNS.designation} filters={filters} onFilter={onFilter} options={designationOptions} />
                {MONTH_LABELS.map((label) => <th key={label} className="num">{label}</th>)}
                <SortHeader label="TOT" sortKey="total" sort={sort} onSort={onSort} className="num" spec={ROW_COLUMNS.total} filters={filters} onFilter={onFilter} />
                <SortHeader label="AVG" sortKey="average_headcount" sort={sort} onSort={onSort} className="num" spec={ROW_COLUMNS.average_headcount} filters={filters} onFilter={onFilter} />
                <SortHeader label="Reading" sortKey="status" sort={sort} onSort={onSort} spec={ROW_COLUMNS.status} filters={filters} onFilter={onFilter} options={statusOptions} />
                <SortHeader label="Net new" sortKey="net_new_vs_base" sort={sort} onSort={onSort} className="num" spec={ROW_COLUMNS.net_new_vs_base} filters={filters} onFilter={onFilter} />
              </tr>
            </thead>
            <tbody>
              {sortRows(block.rows, sort).map((row) => (
                <YearRow
                  key={row.tax_year}
                  row={row}
                  block={block}
                  unreachable={unreachableBy(row.tax_year)}
                  onOpenMonth={onOpenMonth}
                  onOpenYear={onOpenYear}
                  onWhatIf={onWhatIf}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

const PICKER_COLUMNS = {
  name: { key: 'name', label: 'Client', type: TEXT, read: (c) => c.name },
  state: { key: 'state', label: 'State', type: ENUM, read: (c) => c.billing_state },
  employees: { key: 'employees', label: 'Employees', type: NUMERIC, read: (c) => c.employees },
  data: {
    key: 'data', label: 'Data', type: ENUM,
    read: (c) => (c.synthetic ? 'Synthetic' : 'Client payroll'),
  },
};

/** The client list shown at portfolio scope, sortable and filterable (29 Sep). */
function ClientPicker({ clients, onPickClient }) {
  const table = useTableControls(PICKER_COLUMNS, clients);
  return (
    <>
      <FilterBar {...table.bar('clients')} />
      <div className="tcc-table-wrap">
        <table className="tbl tbl-compact">
          <thead>
            <tr>
              <SortHeader {...table.head('name')} />
              <SortHeader {...table.head('state')} />
              <SortHeader {...table.head('employees')} className="num" />
              <SortHeader {...table.head('data')} />
            </tr>
          </thead>
          <tbody>
            {table.rows.map((client) => (
              <tr key={client.account_id}>
                <td>
                  <button className="tcc-link" onClick={() => onPickClient?.(client.account_id)}>
                    {client.name}
                  </button>
                </td>
                <td>{client.billing_state || '—'}</td>
                <td className="num">{client.employees != null ? NUM.format(client.employees) : '—'}</td>
                <td>
                  {client.synthetic
                    ? <span className="pill pill-warn" title="Generated payroll, not a real client">Synthetic</span>
                    : <span className="pill pill-ok">Client payroll</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

export default function TrendGridView({
  scope, scopeOptions, clientScope, scopeError, onPickClient, onOpenUnit, onWhatIf,
}) {
  const [loaded, setLoaded] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [method, setMethod] = useState('min_max');
  const [expanded, setExpanded] = useState({});
  const [detail, setDetail] = useState({});

  const isPortfolio = scope?.clientId === PORTFOLIO;
  const state = useMemo(
    () => trendState(scope, scopeOptions, clientScope),
    [scope, scopeOptions, clientScope],
  );

  // The key a payload belongs to. Rendering is guarded on it, so a slow fetch
  // for the previous client can never paint under the new client's name.
  const scopeKey = `${scope?.clientId ?? ''}|${state ?? ''}|${method}`;

  const load = useCallback(async () => {
    if (isPortfolio || !state) { setLoaded(null); return; }
    setLoading(true);
    setError(null);
    try {
      const body = await fetchClientUnits(scope.clientId, { state, method });
      setLoaded({ key: scopeKey, data: body });
    } catch (err) {
      setLoaded(null);
      setError(String(err.message || err));
    } finally {
      setLoading(false);
    }
  }, [isPortfolio, scope?.clientId, state, method, scopeKey]);

  useEffect(() => { load(); }, [load]);

  // Only render a payload that belongs to the CURRENT scope. Without this the
  // previous client's locations stay on screen for the whole fetch — 3-8s of a
  // grid captioned with someone else's name.
  const payload = loaded?.key === scopeKey ? loaded.data : null;
  const calculated = isCalculated(payload);
  const data = useMemo(
    () => (calculated ? trendFromGold(payload) : null),
    [payload, calculated],
  );

  const runCalculation = useCallback(async () => {
    if (isPortfolio || !scope?.year) return;
    setRunning(true);
    setError(null);
    try {
      await runClientCalculation(scope.clientId, { year: scope.year, state });
      await load();
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setRunning(false);
    }
  }, [isPortfolio, scope?.clientId, scope?.year, state, load]);

  const blocks = useMemo(() => buildBlocks(data), [data]);

  // Sort and filter live in the query string so a driven view is shareable and
  // survives a refresh — the same reason the drill is a route rather than an
  // overlay.
  const [search, setSearch] = useSearchParams();
  const sort = useMemo(() => parseSort(search.get('sort')), [search]);
  const unitFilter = search.get('unit_q') || '';

  const patchSearch = useCallback((patch) => {
    const next = new URLSearchParams(search);
    for (const [key, value] of Object.entries(patch)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    setSearch(next, { replace: true });
  }, [search, setSearch]);

  const onSort = useCallback((key, options) => {
    patchSearch({ sort: formatSort(toggleSort(sort, key, options)) });
  }, [patchSearch, sort]);

  // WI-21. Chosen base years, per location, in the URL. The run's own base is
  // never written there: choosing it again removes the entry.
  const rebaseMap = useMemo(() => parseRebase(search.get('rebase')), [search]);
  const inferredBase = useMemo(
    () => Object.fromEntries(blocks.map((b) => [b.unit_id, b.baseRow?.tax_year ?? null])),
    [blocks],
  );
  const onRebase = useCallback((unitId, year) => {
    const next = { ...rebaseMap };
    if (year == null || year === inferredBase[unitId]) delete next[unitId];
    else next[unitId] = year;
    patchSearch({ rebase: formatRebase(next) });
  }, [rebaseMap, inferredBase, patchSearch]);

  const [rebases, setRebases] = useState({});
  const rebaseKey = (unitId, year) => `${scope?.clientId}|${method}|${unitId}|${year}`;
  useEffect(() => {
    if (isPortfolio || !state || !calculated) return;
    for (const [unitId, year] of Object.entries(rebaseMap)) {
      const key = rebaseKey(unitId, year);
      if (rebases[key]) continue;
      setRebases((prev) => ({ ...prev, [key]: { loading: true, year } }));
      fetchUnitRebase(scope.clientId, unitId, { baseYear: year, method, state })
        .then((data) => setRebases((prev) => ({ ...prev, [key]: { data, year } })))
        .catch((err) => setRebases((prev) => ({ ...prev, [key]: { error: String(err.message || err), year } })));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rebaseMap, scope?.clientId, method, state, calculated, isPortfolio]);

  // WI-21, saved. A recalculation is running from the moment a choice is saved
  // until a run newer than the one on screen lands; poll until it does.
  const [saveStates, setSaveStates] = useState({});
  const [recalc, setRecalc] = useState(null);
  const onSaveBase = useCallback(async (unitId, year, justification) => {
    setSaveStates((prev) => ({ ...prev, [unitId]: { saving: true, year } }));
    try {
      const answer = await saveBaseYear(scope.clientId, unitId, { baseYear: year, justification, state });
      if (!answer?.recorded) {
        setSaveStates((prev) => ({ ...prev, [unitId]: { error: answer?.reason || 'Nothing to change.' } }));
        return;
      }
      setSaveStates((prev) => ({ ...prev, [unitId]: { recalculating: true, year } }));
      setRecalc({ unitId, year, fromRunId: payload?.run?.run_id ?? null });
    } catch (err) {
      setSaveStates((prev) => ({ ...prev, [unitId]: { error: String(err.message || err) } }));
    }
  }, [scope?.clientId, state, payload?.run?.run_id]);

  useEffect(() => {
    if (!recalc) return undefined;
    const timer = setInterval(() => { load(); }, 15000);
    return () => clearInterval(timer);
  }, [recalc, load]);

  useEffect(() => {
    if (!recalc || !payload?.run?.run_id) return;
    if (payload.run.run_id === recalc.fromRunId || payload.newer_run_in_flight) return;
    // The new run has landed. The saved base is now the run's own, so the
    // preview for that location has nothing left to show.
    const next = { ...rebaseMap };
    delete next[recalc.unitId];
    patchSearch({ rebase: formatRebase(next) });
    setRebases({});
    setSaveStates((prev) => ({ ...prev, [recalc.unitId]: null }));
    setRecalc(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [payload, recalc]);

  const pricedBlocks = useMemo(() => blocks.map((block) => {
    const year = rebaseMap[block.unit_id];
    const entry = year != null ? rebases[rebaseKey(block.unit_id, year)] : null;
    return entry?.data ? rebaseBlock(block, entry.data) : block;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [blocks, rebaseMap, rebases, method, scope?.clientId]);

  const rowFilters = useMemo(
    () => parseFilters(ROW_COLUMNS, search.get('row_f')), [search],
  );
  const onFilter = useCallback((column, expr) => {
    const next = { ...rowFilters };
    if (expr) next[column] = expr;
    else delete next[column];
    patchSearch({ row_f: formatFilters(next) });
  }, [patchSearch, rowFilters]);

  // Options come from every row the client holds, NOT from the rows currently
  // surviving the filter — otherwise choosing one status deletes the others
  // from the menu and there is no way back except the URL.
  const allRows = useMemo(() => blocks.flatMap((block) => block.rows), [blocks]);
  const statusOptions = useMemo(
    () => presentValues(allRows, ROW_COLUMNS.status.read), [allRows],
  );
  const yearOptions = useMemo(
    () => presentValues(allRows, ROW_COLUMNS.tax_year.read), [allRows],
  );
  const designationOptions = useMemo(
    () => presentValues(allRows, ROW_COLUMNS.designation.read), [allRows],
  );

  const shownBlocks = useMemo(() => {
    const byUnit = filterBlocks(pricedBlocks, unitFilter);
    if (!Object.keys(rowFilters).length) return byUnit;
    // A block whose every year was filtered out is not an empty location, it is
    // a location with nothing to say under this filter — so it goes entirely
    // rather than rendering as a heading over no rows.
    return byUnit
      .map((block) => ({ ...block, rows: applyFilters(block.rows, ROW_COLUMNS, rowFilters) }))
      .filter((block) => block.rows.length);
  }, [pricedBlocks, unitFilter, rowFilters]);

  const shownRowCount = useMemo(
    () => shownBlocks.reduce((count, block) => count + block.rows.length, 0),
    [shownBlocks],
  );

  // The unit search rides in the same statement as the column filters, so the
  // reader sees one "showing 12 of 37" rather than two disagreeing counts.
  const chipFilters = useMemo(
    () => (unitFilter ? { ...rowFilters, unit: `~${unitFilter}` } : rowFilters),
    [rowFilters, unitFilter],
  );
  const chipSpecs = { ...ROW_COLUMNS, unit: UNIT_COLUMN };
  const clearFilter = useCallback((column) => {
    if (column == null) {
      patchSearch({ row_f: '', unit_q: '' });
      return;
    }
    if (column === 'unit') patchSearch({ unit_q: '' });
    else onFilter(column, '');
  }, [patchSearch, onFilter]);
  const totals = useMemo(() => summariseTrend(data, blocks), [data, blocks]);

  // A month cell is a destination, not a drawer. Same cell semantics, same
  // numbers; the population it opens now has a URL somebody can paste.
  const openDrill = useCallback((block, row, monthIndex) => {
    onOpenUnit?.(block.unit_id, {
      year: row.tax_year,
      month: monthIndex == null ? null : monthIndex + 1,
      method,
    });
  }, [onOpenUnit, method]);

  // Expanded by default. The whole client on one scroll IS the answer — six
  // locations x six years is 36 rows, and its length is the point. Collapsing
  // all but the problem units hid the comparison the grid exists to make.
  useEffect(() => {
    setExpanded(Object.fromEntries(blocks.map((block) => [block.unit_id, true])));
  }, [blocks]);

  if (isPortfolio) {
    // A base year is a fact about ONE client's payroll, so there is no honest
    // portfolio grid — stacking clients would measure each location against
    // somebody else's baseline. What there is instead is a picker with enough
    // on it to choose from, built from `/api/scope` so it costs no engine run.
    const clients = [...(scopeOptions?.clients || [])].sort(
      (a, b) => (a.synthetic === b.synthetic
        ? a.name.localeCompare(b.name)
        : (a.synthetic ? 1 : -1)),
    );

    return (
      <div>
        <div className="tcc-eyebrow">What is it worth</div>
        <h1 className="page-title">Position by location</h1>
        <p className="page-sub">
          Every location a client operates, every year the statute can price, against
          the location&apos;s own base year. Pick a client to open the grid.
        </p>

        <div className="callout info">
          <b>There is no portfolio view of this screen, deliberately.</b> A base year
          is a fact about one client&apos;s payroll; measuring one company&apos;s
          locations against another&apos;s baseline would be arithmetic without a meaning.
        </div>

        <div className="panel">
          <ClientPicker clients={clients} onPickClient={onPickClient} />
          {clients.length === 0 ? (
            scopeError ? (
              // A cold lakehouse can take a minute and then time out. Saying
              // "no clients" for a read that never completed is a different
              // claim, and the wrong one.
              <p className="small tone-warn">
                The client list could not be loaded, so this is not a statement that
                there are none. {scopeError}
              </p>
            ) : (
              <p className="small muted">
                No clients are visible in the active data source.
              </p>
            )
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* One line: breadcrumb sits above, then the title. Method is HERE and not
          in the chrome — Min-Max against Pay Period is 539 eligible employees
          against 656 on the reference client, and the statute has not chosen.
          A dropdown in the top strip reads as a display preference. */}
      <div className="trend-head">
        <h1 className="page-title">Position by location</h1>
        <div className="trend-head-controls">
          {data ? (
            <>
              <label>
                <span className="sr-only">Filter locations</span>
                <input
                  type="search"
                  placeholder="Filter unit, name or FEIN"
                  value={unitFilter}
                  onChange={(event) => patchSearch({ unit_q: event.target.value })}
                />
              </label>
              {sort.length ? (
                <button type="button" className="tcc-link" onClick={() => patchSearch({ sort: '' })}>
                  Clear sort
                </button>
              ) : null}
            </>
          ) : null}
          <MethodTabs method={method} onChange={setMethod} />
        </div>
      </div>

      {loading && !payload ? (
        <div className="panel trend-loading"><Loader2 size={16} className="spin" /> Reading the warehouse…</div>
      ) : null}
      {error ? <div className="callout warn">{error}</div> : null}

      {/* Never $0 and never a bare empty grid: "the pipeline has not reached
          this yet" and "we looked and the answer is nothing" are different
          statements, and only the second is about this client's payroll.
          The button is an override for when you cannot wait for the next
          sweep -- it is not what makes the client exist. */}
      {payload && !calculated ? (
        <div className="panel trend-uncalculated">
          <h2 className="panel-title">Awaiting the next run</h2>
          <p className="page-sub">
            {payload.message
              || `Payroll is held for this client, but TY${scope?.year} has not been
                  assessed yet. It carries no figure — not a zero.`}
          </p>
          <button
            type="button"
            className="tcc-btn tcc-btn-primary"
            onClick={runCalculation}
            disabled={running || !scope?.year}
          >
            {running
              ? <><Loader2 size={14} className="spin" /> Running…</>
              : <>Run TY{scope?.year} now</>}
          </button>
        </div>
      ) : null}

      {data ? (
        <>
          {/* 29 Sep: the banner restated this line in large type. The counts
              stay as the caption; the conditions on them sit behind the (i),
              and the story is the Copilot summary, opened on demand. */}
          <InsightBar
            caption={(
              <p className="figure-line">
                <b>{totals.locations}</b> locations
                <span>·</span>
                <b>{totals.qualifyingLocations}</b> qualify
                {totals.attentionLocations ? (
                  <>
                    <span>·</span>
                    <b className="amber">{totals.attentionLocations}</b> below the minimum
                  </>
                ) : null}
                {totals.openYear ? (
                  <>
                    <span>·</span>
                    {/* A forecast about the open year, kept apart from the verdicts. */}
                    <em className="figure-forecast" title={`TY${totals.openYear} is still open: read on its closed months, nothing claimable until it closes`}>
                      <b>{totals.onTrackLocations}</b> of {totals.openLocations} on track in TY{totals.openYear}
                    </em>
                  </>
                ) : null}
                <span>·</span>
                <b>{USD.format(totals.annualCreditUsd)}</b> claimable
                <span>·</span>
                <b>{USD.format(totals.lifetimeUsd)}</b> if maintained
                <span>·</span>
                {totals.yearRange}
              </p>
            )}
            notes={[
              'Base year and tier are both unconfirmed — the base year is inferred from the payroll rather than supplied, and tier assignment is prototype data.',
              totals.openYear
                ? `TY${totals.openYear} is still open — read on its closed months, never priced${placeholderYears(scopeOptions, scope?.programCode).includes(totals.openYear)
                  ? `, and its wage floor is a placeholder carried forward from TY${totals.openYear - 1}`
                  : ''}.`
                : null,
              totals.declinedYears.length
                ? `${totals.declinedYears.length} year(s) not priced: ${totals.declinedYears.map((d) => `TY${d.tax_year} ${d.reason}`).join(' · ')}`
                : null,
              provenanceLine(payload.run),
            ]}
            request={{ page: 'client', clientId: scope?.clientId, state, method }}
          />
          {payload.newer_run_in_flight ? (
            <p className="small muted">A newer run is in flight.</p>
          ) : null}
          <FilterBar
            specs={chipSpecs}
            filters={chipFilters}
            shown={shownRowCount}
            total={allRows.length}
            noun="location-years"
            onClear={clearFilter}
          />

          {shownBlocks.length ? shownBlocks.map((block) => (
            <UnitBlock
              key={block.unit_id}
              block={block}
              expanded={!!expanded[block.unit_id]}
              detail={!!detail[block.unit_id]}
              unreachableBy={(taxYear) => unreachableFor(data, taxYear)}
              sort={sort}
              onSort={onSort}
              filters={rowFilters}
              onFilter={onFilter}
              statusOptions={statusOptions}
              yearOptions={yearOptions}
              designationOptions={designationOptions}
              onToggle={(id) => setExpanded((prev) => ({ ...prev, [id]: !prev[id] }))}
              onToggleDetail={(id) => setDetail((prev) => ({ ...prev, [id]: !prev[id] }))}
              onOpenMonth={(b, row, index) => openDrill(b, row, index)}
              onOpenYear={(b, row) => openDrill(b, row, null)}
              // What-if prices against the run's base; on a rebased block it
              // would disagree with the row it was opened from.
              onWhatIf={onWhatIf && !block.rebased
                ? (b, row) => onWhatIf(whatIfLink(row, { unitId: b.unit_id, method }))
                : undefined}
              baseChoices={baseYearChoices(blocks.find((b) => b.unit_id === block.unit_id) || block)}
              inferredBaseYear={inferredBase[block.unit_id]}
              onRebase={onRebase}
              onSaveBase={onSaveBase}
              saveState={saveStates[block.unit_id]}
              rebaseState={rebaseMap[block.unit_id] != null
                ? rebases[rebaseKey(block.unit_id, rebaseMap[block.unit_id])]
                : null}
            />
          )) : (
            <div className="panel">
              <TrendingUp size={16} />{' '}
              {Object.keys(chipFilters).length
                ? 'No location-year matches those filters. Clear them to see the grid.'
                : 'No locations resolved for this client and state.'}
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
