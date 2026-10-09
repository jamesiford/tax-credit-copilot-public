import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle, Check, Loader2, Plus,
} from 'lucide-react';
import { fetchEmployeeProximity } from '../api.js';
import { MAX_STACK, stackEntry } from '../lib/whatIf.js';
import { designationCode, designationTitle } from '../lib/trendGrid.js';
import { ENUM, NUMERIC, TEXT } from '../lib/gridFilter.js';
import SortHeader from './SortHeader.jsx';
import { FilterBar } from './ColumnFilter.jsx';
import useTableControls from './useTableControls.js';
import StackBar from './StackBar.jsx';
import { PORTFOLIO, derivedJurisdictions } from '../lib/scopeDimension.js';

/**
 * Near the line — which employees are close to qualifying, and what closes it.
 *
 * The partner, 27 August 2026, twice and unprompted: *"It's just those ones
 * that are on the edge that if we can scoop more in, that's always good."* And:
 * *"these are the people that are almost part-time or almost full-time, because
 * maybe you can work them a little bit more to get them over the edge."*
 *
 * The engine has always known this and never said it. This view is the read.
 *
 * **It reads an eligibility result and never alters one.** Everything here is
 * arithmetic against `/api/proximity`, which runs the same certified methods and
 * takes their per-employee averages. Nothing on this screen can move 539 / 656.
 *
 * Two distinctions carried through from the calculation, because collapsing
 * either turns an instruction into a wrong instruction:
 *
 * - **The tests fail independently.** "Work them more hours" is useless advice
 *   for somebody already at 40 hours who is simply paid too little, so the
 *   failure modes are shown apart rather than as one count of "ineligible".
 * - **Extra hours pay at the employee's own rate.** Below the threshold rate the
 *   wage floor binds harder than the hours floor, and the honest lever is a
 *   raise. Those rows say so instead of quoting an implausible week.
 */

const BANDS = [1, 2, 5, 10];
const num = (v) => (Number.isFinite(Number(v)) ? Number(v) : 0);
const hrs = (v) => `${num(v).toFixed(2)}h`;
const usd = (v) => `$${num(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
/**
 * A count, for display.
 *
 * Every figure on this screen came off the payload raw — `payload.ineligible
 * .toLocaleString()` — so a response that legitimately omits them threw during
 * render and, with no boundary above it, blanked the entire client page. The
 * cause is handled above; this makes the same mistake un-repeatable.
 */
const count = (v) => num(v).toLocaleString();
/**
 * Hourly rates keep their cents. The Georgia 2023 threshold rate is $18.17;
 * rendering it as "$18" puts an employee earning $18.10 on the wrong side of a
 * line the screen claims to be showing.
 */
const rate = (v) => `$${num(v).toFixed(2)}`;

const MODE_LABEL = {
  hours_only: 'Hours only',
  wages_only: 'Wages only',
  both: 'Both tests',
};

/**
 * The cohort's columns, for sort and filter (29 Sep). Location filters on
 * EVERY site a person works at, so an employee split across two shows under
 * both; it sorts on the one they work at most, which is the one shown.
 */
const STANDALONE_COLUMNS = {
  employee_id: { key: 'employee_id', label: 'Employee', type: TEXT, read: (r) => r.employee_id },
  failure_mode: {
    key: 'failure_mode', label: 'Failing', type: ENUM, read: (r) => r.failure_mode,
    format: (v) => MODE_LABEL[v] || v,
  },
  avg_weekly_hours: { key: 'avg_weekly_hours', label: 'Avg hrs/wk', type: NUMERIC, read: (r) => r.avg_weekly_hours },
  avg_weekly_wages: { key: 'avg_weekly_wages', label: 'Avg $/wk', type: NUMERIC, read: (r) => r.avg_weekly_wages },
  implied_hourly_rate: { key: 'implied_hourly_rate', label: 'Rate', type: NUMERIC, read: (r) => r.implied_hourly_rate },
  additional_weekly_hours: {
    key: 'additional_weekly_hours', label: 'Full-year gap', type: NUMERIC, read: (r) => r.additional_weekly_hours,
  },
};

const COHORT_COLUMNS = {
  ...STANDALONE_COLUMNS,
  worksite_id: {
    key: 'worksite_id', label: 'Location', type: ENUM, multi: true,
    read: (r) => (r.worksites?.length ? r.worksites : (r.worksite_id ? [r.worksite_id] : [])),
    sortValue: (r) => r.worksite_id,
  },
  rest_of_year: {
    key: 'rest_of_year', label: 'Rest of year', type: NUMERIC,
    // Only an open rest of year has a figure; on pace or closed sorts last.
    read: (r) => (r.rest_of_year?.state === 'open' ? r.rest_of_year.additional_weekly_hours : null),
  },
};

/** The instruction for one employee, in the lever that actually applies. */
function Instruction({ row }) {
  if (row.additional_weekly_hours == null) {
    return (
      <span className="prox-instruction unknown">
        No hourly rate on record — cannot price extra hours
      </span>
    );
  }
  if (row.rate_limited) {
    return (
      <span
        className="prox-instruction limited"
        title={`Paid below the ${rate(row.threshold_hourly_rate)}/hr threshold rate, so more hours alone would take an implausible week.`}
      >
        <AlertTriangle size={12} />
        {' '}
        {hrs(row.additional_weekly_hours)}/wk — a raise is the better lever
        {row.hourly_rate_to_qualify
          ? ` (${rate(row.hourly_rate_to_qualify)}/hr qualifies at today's hours)`
          : ''}
      </span>
    );
  }
  return (
    <span className="prox-instruction">
      <strong>+{hrs(row.additional_weekly_hours)}/wk</strong>
      {row.exceeds_plausible_week
        ? <span className="muted"> → {hrs(row.projected_weekly_hours)}</span>
        : null}
    </span>
  );
}

/**
 * What the rest of the year needs, in the partner's words: "+N h/wk for the
 * remaining K pay periods." Read as of the checkpoint, so it is larger than
 * the full-year gap once most of the year is gone.
 *
 * One line (30 Sep). "for the remaining 8 pay periods" was the same on almost
 * every row and wrapped every row to two lines; the column header carries the
 * common count, and a row says its own only where it differs.
 */
function RestOfYear({ rest, periods: usual }) {
  if (!rest) return <span className="muted">—</span>;
  if (rest.state === 'closed') return <span className="prox-instruction unknown">The year is closed</span>;
  if (rest.state === 'on_pace') {
    return <span className="prox-instruction">On pace at the checkpoint ({hrs(rest.pace_weekly_hours)}/wk)</span>;
  }
  if (rest.state !== 'open') {
    return <span className="prox-instruction unknown">{rest.note || 'Nothing to measure yet'}</span>;
  }
  if (rest.rate_limited) {
    return (
      <span className="prox-instruction limited">
        <AlertTriangle size={12} />
        {' '}A raise is the better lever
        {rest.hourly_rate_to_qualify ? ` — ${rate(rest.hourly_rate_to_qualify)}/hr` : ''}
      </span>
    );
  }
  const periods = rest.remaining_pay_periods;
  return (
    <span
      className="prox-instruction"
      title={`+${hrs(rest.additional_weekly_hours)}/wk for the remaining ${periods} pay period${periods === 1 ? '' : 's'}`
        + (rest.exceeds_plausible_week ? ` — ${hrs(rest.needed_weekly_hours)}/wk in all` : '')}
    >
      <strong>+{hrs(rest.additional_weekly_hours)}/wk</strong>
      {rest.exceeds_plausible_week ? <span className="muted"> → {hrs(rest.needed_weekly_hours)}</span> : null}
      {periods !== usual ? <span className="muted"> · {periods} period{periods === 1 ? '' : 's'}</span> : null}
    </span>
  );
}

/** The pay periods most rows have left — the one the column header states. */
function usualPeriods(cohort) {
  const seen = new Map();
  for (const row of cohort || []) {
    const n = row.rest_of_year?.state === 'open' ? row.rest_of_year.remaining_pay_periods : null;
    if (n != null) seen.set(n, (seen.get(n) || 0) + 1);
  }
  let best = null;
  for (const [n, c] of seen) if (best == null || c > seen.get(best)) best = n;
  return best;
}

export default function ProximityView({ scope, scopeOptions, embedded = false, stack = null, yearOpen = false }) {
  const [band, setBand] = useState(5);
  const [method, setMethod] = useState('min_max');
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  // Rows ticked for "Add selected". Cleared whenever the list itself changes,
  // so a tick can never land on a row that is no longer the one shown.
  const [selected, setSelected] = useState(() => new Set());

  // Jurisdiction is DERIVED from the programme, never carried on the scope
  // object — `reconcileScope` does not set it. Reading `scope.jurisdiction`
  // yields undefined and the view silently renders its empty state forever.
  // One helper, shared with the scope bar, so the two cannot disagree about
  // which jurisdiction a programme implies.
  const state = useMemo(() => {
    const found = derivedJurisdictions(scope, scopeOptions);
    return found.length === 1 ? found[0].code : null;
  }, [scope, scopeOptions]);
  const year = scope.year;
  const isPortfolio = scope.clientId === PORTFOLIO;

  const clientName = useMemo(() => {
    const clients = scopeOptions?.clients || [];
    return clients.find((c) => String(c.account_id) === String(scope.clientId))?.name
      || `Account ${scope.clientId}`;
  }, [scope.clientId, scopeOptions]);

  useEffect(() => {
    if (!state || !year || isPortfolio) { setData(null); return undefined; }
    let cancelled = false;
    setLoading(true);
    setError(null);
    // Coverage travels with its scope. Rendering a payload fetched under a
    // previous client under the current client's heading is the bug this
    // pattern exists to prevent — it has shipped nine times.
    const requested = { state, year, method, band, clientId: scope.clientId };
    fetchEmployeeProximity({
      taxYear: year,
      state,
      method,
      within: band,
      limit: 100,
      accountId: isPortfolio ? null : scope.clientId,
      // Embedded in How am I doing, the question is asked at the checkpoint.
      restOfYear: embedded,
    })
      .then((payload) => { if (!cancelled) setData({ key: requested, data: payload }); })
      .catch((e) => { if (!cancelled) { setError(e.message); setData(null); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [state, year, method, band, scope.clientId, isPortfolio]);

  const fresh = data
    && data.key.state === state
    && data.key.year === year
    && data.key.method === method
    && data.key.band === band
    && data.key.clientId === scope.clientId;
  const payload = fresh ? data.data : null;
  // The band counts do not depend on the band chosen, so the chips keep them
  // while a new band loads — but only for the same client, year and method.
  const bandCounts = data
    && data.key.state === state && data.key.year === year
    && data.key.method === method && data.key.clientId === scope.clientId
    ? data.data.bands : null;

  useEffect(() => { setSelected(new Set()); }, [payload]);

  // Sort and filter the cohort. Server order (closest first) stands until a
  // header is clicked. "Select all" and "Add selected" act on what is SHOWN,
  // so filtering to one location and adding everyone is the workflow for
  // lifting that location over its minimum.
  const table = useTableControls(embedded ? COHORT_COLUMNS : STANDALONE_COLUMNS, payload?.cohort);
  const restPeriods = useMemo(() => usualPeriods(payload?.cohort), [payload]);

  // The stack belongs to one year and method; a stack built under another is
  // not this list's, and adding here starts a new one (ClientPage decides).
  const stacking = embedded && !!stack;
  const sameStack = stacking && stack.year === year && stack.method === method;
  const inStack = (token) => sameStack && stack.tokens.has(token);
  const stackSize = sameStack ? stack.tokens.size : 0;
  const addable = table.rows.filter((row) => stackEntry(row) && !inStack(row.record_token));
  const ticked = addable.filter((row) => selected.has(row.record_token));
  const toggle = (token) => setSelected((prev) => {
    const next = new Set(prev);
    if (next.has(token)) next.delete(token); else next.add(token);
    return next;
  });
  const allTicked = addable.length > 0 && ticked.length === addable.length;
  const add = (rows) => {
    stack.onAdd(rows, { taxYear: year, method });
    setSelected(new Set());
  };

  if (!state || !year) {
    return (
      <div className="callout info">
        Select a single program so the cohort is measured against one statute.
        Employees from two programmes cannot share a list — the hours and wage
        floors differ, so they would be ranked against different rulers.
      </div>
    );
  }

  return (
    <div className="prox-view">
      <header className="prox-header">
        <div>
          <h2>Near the line</h2>
          <p className="prox-sub">
            {embedded ? (
              yearOpen ? (
                <>
                  Measured over the {year} payroll so far — the year is still open ·{' '}
                  {method === 'min_max' ? 'Min-Max' : 'Pay Period'} denominator
                </>
              ) : (
                <>
                  Measured across the whole of {year}, not the closed months the
                  verdict above uses ·{' '}
                  {method === 'min_max' ? 'Min-Max' : 'Pay Period'} denominator
                </>
              )
            ) : (
              <>
                {isPortfolio ? 'All accounts' : clientName} · {state} · {year} ·{' '}
                {method === 'min_max' ? 'Min-Max' : 'Pay Period'} denominator
              </>
            )}
          </p>
        </div>
        <div className="prox-controls">
          <label>
            Method
            <select value={method} onChange={(e) => setMethod(e.target.value)}>
              <option value="min_max">Min-Max</option>
              <option value="pay_period">Pay Period</option>
            </select>
          </label>
          {/* One control for the band (30 Sep). A "Within" dropdown and a row
              of band chips used to set the same thing twice; the chips carry
              each band's count, so they are the one that stays. */}
          <div className="prox-bands" role="group" aria-label="Within hours a week of the line">
            <span className="prox-bands-label" aria-hidden="true">Within</span>
            {(bandCounts || BANDS.map((b) => ({ within_weekly_hours: b, employees: null }))).map((b) => (
              <button
                type="button"
                key={b.within_weekly_hours}
                className={`prox-band${b.within_weekly_hours === band ? ' active' : ''}`}
                aria-pressed={b.within_weekly_hours === band}
                onClick={() => setBand(b.within_weekly_hours)}
              >
                <span className="prox-band-label">{b.within_weekly_hours}h</span>
                {b.employees != null ? <span className="prox-band-count">{b.employees}</span> : null}
              </button>
            ))}
          </div>
        </div>
      </header>

      {/* A cohort is a fact about ONE client's run: the floors, the fiscal
          window and the recorded verdicts all belong to it. Portfolio scope
          used to answer anyway, from the configured tenant, and label account
          1001's employees "All accounts". Embedded, the parent has already
          said this — two callouts stacked reads as two different problems. */}
      {isPortfolio && !embedded ? (
        <div className="callout info">
          Select one client to see who is near the line. The cohort is read from
          that client&rsquo;s run — its statute, its fiscal window, its recorded
          verdicts — so there is no portfolio version of it. What-if ranks whole
          clients by jobs to threshold instead.
        </div>
      ) : null}

      {loading ? (
        <div className="prox-loading"><Loader2 size={16} className="spin" /> Calculating…</div>
      ) : null}

      {error ? <div className="prox-error">{error}</div> : null}

      {/* A year this client has no calculated run for. The endpoint answers 200
          and says so in `calculation_state` rather than 404-ing, because "we
          have not priced this" is a different fact from "this does not exist" —
          but every figure below is then absent, and reading `.toLocaleString()`
          off an absent one threw and took the WHOLE CLIENT PAGE down to a blank
          screen. Candle Bottle holds one fiscal year and the scope opens on the
          next, so the real client was the one that white-screened. */}
      {payload && payload.calculation_state === 'not_calculated' ? (
        <div className="callout info">
          No calculated run holds {state} {year} for{' '}
          {isPortfolio ? 'this selection' : clientName}, so there is no cohort to
          rank. That is not a zero — this year has not been priced. Choose a year
          this client has payroll and an authored statute for.
        </div>
      ) : null}

      {payload && payload.calculation_state !== 'not_calculated' ? (
        <>
          {/* Two lines where there were five cards, a callout and a chip row
              (30 Sep). Still in the same order: who is within reach first,
              then the three ways of failing kept apart, then the ruler. */}
          <p className="prox-summary">
            <strong className="prox-summary-lead">{count(payload.within_band)} within reach</strong>
            {' '}— {band} or fewer more hours a week to qualify · {count(payload.ineligible)} of{' '}
            {count(payload.evaluated)} evaluated are not eligible:{' '}
            <span className="prox-summary-mode hours_only"><b>{count(payload.failure_modes?.hours_only)}</b> hours only</span>,{' '}
            <span className="prox-summary-mode wages_only"><b>{count(payload.failure_modes?.wages_only)}</b> wages only</span>,{' '}
            <span className="prox-summary-mode both"><b>{count(payload.failure_modes?.both)}</b> both tests</span>
          </p>

          <p className="prox-floors">
            Georgia {payload.floors.tax_year} requires{' '}
            <strong>{payload.floors.minimum_average_weekly_hours} hrs/week</strong> and{' '}
            <strong>{usd(payload.floors.minimum_average_weekly_wages_usd)}/week</strong>
            {payload.floors.threshold_hourly_rate
              ? <> — an effective floor of <strong>{rate(payload.floors.threshold_hourly_rate)}/hr</strong></>
              : null}
            . Resolved from <code>{payload.floors.source}</code>.
          </p>

          {/* The What-if stack (28 Sep). Tick several and add them at once, or
              add one row at a time; the stack is projected together. */}
          {stacking ? (
            <StackBar
              ticked={ticked.length}
              onAddSelected={() => add(ticked)}
              stackSize={stackSize}
              onOpen={() => stack.onOpen()}
            />
          ) : null}

          <FilterBar {...table.bar('employees')} />

          <table className="prox-table">
            <thead>
              <tr>
                {stacking ? (
                  <th className="prox-tick">
                    <input
                      type="checkbox"
                      aria-label="Select every row that can be added"
                      checked={allTicked}
                      disabled={!addable.length}
                      onChange={() => setSelected(allTicked ? new Set() : new Set(addable.map((r) => r.record_token)))}
                    />
                  </th>
                ) : null}
                <SortHeader {...table.head('employee_id')} />
                {embedded ? <SortHeader {...table.head('worksite_id')} /> : null}
                <SortHeader {...table.head('failure_mode')} />
                <SortHeader {...table.head('avg_weekly_hours')} className="num" />
                <SortHeader {...table.head('avg_weekly_wages')} className="num" />
                <SortHeader {...table.head('implied_hourly_rate')} className="num" />
                <SortHeader
                  {...table.head('additional_weekly_hours', {
                    // An open year's cohort is measured on the payroll so far,
                    // so its gap is to date, not over a year that has not run.
                    label: embedded && yearOpen ? 'Gap to date' : 'Full-year gap',
                  })}
                />
                {embedded ? (
                  <SortHeader
                    {...table.head('rest_of_year', {
                      label: payload.rest_of_year_as_of
                        ? (
                          <>
                            Rest of year{' '}
                            <span className="th-sub">
                              {restPeriods != null ? `${restPeriods} pay periods ` : ''}from {payload.rest_of_year_as_of}
                            </span>
                          </>
                        )
                        : 'Rest of year',
                    })}
                  />
                ) : null}
                {stacking ? <th aria-label="What-if stack" /> : null}
              </tr>
            </thead>
            <tbody>
              {table.rows.map((row) => {
                const entry = stacking ? stackEntry(row) : null;
                const stacked = entry && inStack(row.record_token);
                const withYear = { ...row, tax_year: year };
                return (
                <tr key={row.employee_id} className={stacked ? 'prox-stacked' : undefined}>
                  {stacking ? (
                    <td className="prox-tick">
                      {entry && !stacked ? (
                        <input
                          type="checkbox"
                          aria-label={`Select ${row.employee_id}`}
                          checked={selected.has(row.record_token)}
                          onChange={() => toggle(row.record_token)}
                        />
                      ) : null}
                    </td>
                  ) : null}
                  <td className="mono">{row.employee_id}</td>
                  {embedded ? (
                    <td className="prox-where">
                      {row.worksite_id ? (
                        <>
                          <span title={row.worksites?.length > 1 ? `Also works at ${row.worksites.filter((w) => w !== row.worksite_id).join(', ')}` : undefined}>
                            {row.worksite_id}{row.worksites?.length > 1 ? ` +${row.worksites.length - 1}` : ''}
                          </span>
                          {' '}
                          <span className={`pill ${designationCode(withYear) === 'Unassigned' ? 'pill-neutral' : 'pill-accent'}`} title={designationTitle(withYear)}>
                            {designationCode(withYear)}
                          </span>
                        </>
                      ) : '—'}
                    </td>
                  ) : null}
                  <td>
                    <span className={`prox-mode ${row.failure_mode}`}>
                      {MODE_LABEL[row.failure_mode] || row.failure_mode}
                    </span>
                  </td>
                  <td className="num">
                    {hrs(row.avg_weekly_hours)}
                    {row.hours_gap_per_week > 0
                      ? <span className="prox-gap"> −{hrs(row.hours_gap_per_week)}</span>
                      : null}
                  </td>
                  <td className="num">
                    {usd(row.avg_weekly_wages)}
                    {row.wages_gap_per_week > 0
                      ? <span className="prox-gap"> −{usd(row.wages_gap_per_week)}</span>
                      : null}
                  </td>
                  <td className="num">
                    {row.implied_hourly_rate == null ? '—' : rate(row.implied_hourly_rate)}
                  </td>
                  <td><Instruction row={row} /></td>
                  {embedded ? <td><RestOfYear rest={row.rest_of_year} periods={restPeriods} /></td> : null}
                  {stacking ? (
                    <td>
                      {stacked ? (
                        <button
                          type="button"
                          className="btn btn-secondary prox-whatif on"
                          onClick={() => stack.onRemove(row.record_token)}
                          aria-label={`Remove ${row.employee_id} from the What-if stack`}
                          title="In the What-if stack — click to remove"
                        >
                          <Check size={13} /> Stacked
                        </button>
                      ) : entry ? (
                        <button
                          type="button"
                          className="btn btn-secondary prox-whatif"
                          disabled={stackSize >= MAX_STACK}
                          onClick={() => add([row])}
                          aria-label={`Add ${row.employee_id} to the What-if stack`}
                          title={entry.raise
                            ? `Pre-filled: +${entry.hours} hrs/wk and a $${entry.raise.toFixed(2)}/hr raise for the rest of the year`
                            : `Pre-filled: +${entry.hours} hrs/wk for the rest of the year`}
                        >
                          <Plus size={13} /> Add
                        </button>
                      ) : null}
                    </td>
                  ) : null}
                </tr>
                );
              })}
            </tbody>
          </table>

          {payload.cohort.length === 0 ? (
            <div className="prox-empty">
              Nobody is within {band} hours a week of the line. Widen the band above.
            </div>
          ) : table.rows.length === 0 ? (
            <div className="prox-empty">No one in this list matches the filter.</div>
          ) : null}

          <p className="prox-method">{payload.method_note}</p>
        </>
      ) : null}
    </div>
  );
}
