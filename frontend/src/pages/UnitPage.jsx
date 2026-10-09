import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Check, Loader2, MapPin, Plus } from 'lucide-react';
import { fetchClientUnit, isCalculated } from '../api.js';
import { MONTH_LABELS, fmtHeadcount } from '../lib/trendGrid.js';
import { MAX_STACK, stackEntry } from '../lib/whatIf.js';
import useWhatIfStack from '../components/useWhatIfStack.js';
import StackBar from '../components/StackBar.jsx';
import { MONEY } from '../lib/reference.js';
import { NUMERIC, TEXT, formatFilters, parseFilters } from '../lib/gridFilter.js';
import Breadcrumb from '../components/Breadcrumb.jsx';
import PageHeader from '../components/PageHeader.jsx';
import StatCard, { StatRow } from '../components/StatCard.jsx';
import InsightBar, { provenanceLine } from '../components/InsightBar.jsx';
import MethodTabs from '../components/MethodTabs.jsx';
import GridTabs, { GridTabPanel } from '../components/GridTabs.jsx';
import { ColumnFilter, FilterBar } from '../components/ColumnFilter.jsx';

/** How close counts as close. A presentation choice, so it lives here. */
const BAND = 5;

const num = (v) => (Number.isFinite(Number(v)) ? Number(v) : 0);

/**
 * The filterable employee columns.
 *
 * Keys are the wire names the endpoint whitelists, so a control here cannot
 * name a column the SQL will refuse. `read` is only for the chip label and the
 * tests — the narrowing itself happens in the warehouse, never over these rows.
 */
const EMPLOYEE_COLUMNS = {
  employee_id: { key: 'employee_id', label: 'Employee', type: TEXT, read: (r) => r.employee_id },
  weeks_worked: { key: 'weeks_worked', label: 'Weeks', type: NUMERIC, read: (r) => r.weeks_worked },
  total_hours: { key: 'total_hours', label: 'Total hrs', type: NUMERIC, read: (r) => r.total_hours },
  avg_weekly_hours: {
    key: 'avg_weekly_hours', label: 'Avg weekly hrs', type: NUMERIC, read: (r) => r.avg_weekly_hours,
  },
  avg_weekly_wages: {
    key: 'avg_weekly_wages', label: 'Avg weekly wages', type: NUMERIC, read: (r) => r.avg_weekly_wages,
  },
};

/**
 * Calendar months, which are NOT `MONTH_LABELS`.
 *
 * The grid's labels are fiscal POSITIONS — M1 is whichever calendar month the
 * client's window opens in. Reusing them here would print a real date as
 * "2 M1 23".
 */
const CALENDAR_MONTHS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

/** `2023-08-01` → `1 Aug 23`. Two dates have to share one column at 1024. */
export function shortDate(value) {
  if (!value) return null;
  const date = new Date(`${String(value).slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return null;
  const year = String(date.getUTCFullYear()).slice(2);
  return `${date.getUTCDate()} ${CALENDAR_MONTHS[date.getUTCMonth()]} ${year}`;
}

/**
 * One location, at one tax year, optionally narrowed to one month.
 *
 * This was a drawer inside the client grid, which meant the thing a reviewer
 * was actually reading had no URL. `month` NARROWS the population server-side
 * rather than annotating it, so the count here is the number of people the
 * statute counts — 25 at Cascade's GA_GA-001 in month 5, not the 29 who worked
 * there that year.
 *
 * The two cohorts are TABS, not stacked panels. They are genuine peers — who
 * counted, and who did not — and stacked, the second sat a screen below the
 * figure that motivates it. Counted opens first: it is what the page title
 * claims to show and what the credit is computed from, and defaulting to a
 * lead list would make the statutory answer the thing you have to go and find.
 */
export default function UnitPage({
  clientId, unitId, year, month, method = 'min_max', state,
  clientName, onOpenEmployee, onOpenClient, onOpenPortfolio, onChangeMonth,
  onChangeMethod,
}) {
  const [loaded, setLoaded] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  // Sort, both filter sets and the open tab live in the query string, so a
  // driven view is shareable and survives a refresh — the same reason the drill
  // is a route rather than an overlay.
  const [search, setSearch] = useSearchParams();
  const tab = search.get('tab') === 'near' ? 'near' : 'people';
  const sortField = search.get('esort') || 'avg_weekly_hours';
  const sortDir = search.get('eorder') === 'asc' ? 'asc' : 'desc';
  const empFilters = useMemo(
    () => parseFilters(EMPLOYEE_COLUMNS, search.get('emp_f')), [search],
  );
  const nearFilters = useMemo(
    () => parseFilters(EMPLOYEE_COLUMNS, search.get('near_f')), [search],
  );
  const empWire = formatFilters(empFilters);
  const nearWire = formatFilters(nearFilters);

  const patchSearch = useCallback((patch) => {
    const next = new URLSearchParams(search);
    for (const [name, value] of Object.entries(patch)) {
      if (value) next.set(name, value);
      else next.delete(name);
    }
    setSearch(next, { replace: true });
  }, [search, setSearch]);

  const setFilter = useCallback((param, current, column, expr) => {
    if (column == null) {
      patchSearch({ [param]: '' });
      return;
    }
    const next = { ...current };
    if (expr) next[column] = expr;
    else delete next[column];
    patchSearch({ [param]: formatFilters(next) });
  }, [patchSearch]);

  const key = `${clientId}|${unitId}|${year}|${month ?? ''}|${method}`
    + `|${sortField}|${sortDir}|${empWire}|${nearWire}`;
  // The request in flight. A slower earlier read must be DISCARDED, not stored:
  // guarding only the render still lets it overwrite the newer payload, which
  // blanks a correct page instead of showing a wrong one.
  const latest = useRef(key);

  const load = useCallback(async () => {
    if (!clientId || !unitId || !year) return;
    latest.current = key;
    // Cleared BEFORE the fetch, not after it resolves: a cold read is slow
    // enough that the previous unit's people would otherwise sit under this
    // unit's heading for seconds.
    setLoaded(null);
    setError(null);
    setLoading(true);
    try {
      const body = await fetchClientUnit(clientId, unitId, {
        year, month, method, state,
        sort: sortField, order: sortDir, filter: empWire, nearFilter: nearWire,
      });
      if (latest.current !== key) return;
      setLoaded({ key, data: body });
    } catch (reason) {
      if (latest.current !== key) return;
      setError(String(reason.message || reason));
    } finally {
      if (latest.current === key) setLoading(false);
    }
  }, [clientId, unitId, year, month, method, state, sortField, sortDir, empWire, nearWire, key]);

  useEffect(() => { load(); }, [load]);

  const payload = loaded?.key === key ? loaded.data : null;
  const calculated = isCalculated(payload);
  const employees = payload?.employees || [];
  const near = payload?.near_threshold || [];
  const unit = payload?.unit || null;
  const monthIndex = month == null ? null : Number(month) - 1;

  const trail = [
    { key: 'p', label: 'Portfolio', onClick: onOpenPortfolio },
    { key: 'c', label: clientName || `Account ${clientId}`, onClick: onOpenClient },
    { key: 'u', label: unitId },
  ];

  const floor = payload?.thresholds?.min_weekly_hours ?? null;
  const wageFloor = payload?.thresholds?.min_weekly_wages ?? null;
  const inBand = useMemo(
    () => (floor == null ? [] : near.filter((r) => num(r.avg_weekly_hours) >= floor - BAND)),
    [near, floor],
  );

  // 29 Sep: a near-the-floor person can go straight into the What-if stack,
  // one at a time or ticked together. Only an OPEN year has a rest of it, so a
  // closed year offers no lever — the same rule Near the line follows.
  const navigate = useNavigate();
  const stack = useWhatIfStack({ clientId, taxYear: year, method });
  const [selected, setSelected] = useState(() => new Set());
  useEffect(() => { setSelected(new Set()); }, [payload]);
  const stackable = near.some((r) => stackEntry(r));
  const addable = near.filter((r) => stackEntry(r) && !stack.tokens.has(r.record_token));
  const ticked = addable.filter((r) => selected.has(r.record_token));
  const allTicked = addable.length > 0 && ticked.length === addable.length;
  const toggle = (token) => setSelected((prev) => {
    const next = new Set(prev);
    if (next.has(token)) next.delete(token); else next.add(token);
    return next;
  });
  const addToStack = (rows) => { stack.add(rows); setSelected(new Set()); };

  // The denominators. A filter narrows the LIST, never the location's answer,
  // so every headline figure reads the unfiltered count the API reports rather
  // than counting the rows that survived.
  const countedTotal = payload?.total_unfiltered ?? employees.length;
  const nearTotal = payload?.near_total_unfiltered ?? near.length;

  // Weight is the fraction of an employee allocated to this location. It is
  // 1.00 for almost everybody, and a column of 1.00 costs the same width as one
  // that says something — so it appears only where it varies, the same rule the
  // client grid applies to tier.
  const showShare = useMemo(
    () => employees.some((person) => person.weight != null && num(person.weight) !== 1),
    [employees],
  );

  const onSort = useCallback((field) => {
    const flip = sortField === field && sortDir === 'desc' ? 'asc' : 'desc';
    patchSearch({ esort: field, eorder: flip });
  }, [patchSearch, sortField, sortDir]);
  const sort = { field: sortField, dir: sortDir };

  const empFilter = (column, expr) => setFilter('emp_f', empFilters, column, expr);
  const nearFilter = (column, expr) => setFilter('near_f', nearFilters, column, expr);

  const tabs = [
    {
      id: 'people',
      label: 'Counted',
      count: countedTotal,
      hint: 'Employees the statute counted toward the credit at this location',
    },
    {
      id: 'near',
      label: 'Near the floor',
      count: nearTotal,
      hint: 'Employees with payroll here who did not qualify, closest first',
    },
  ];

  return (
    <div>
      <Breadcrumb trail={trail} />

      <PageHeader
        eyebrow="What is it worth"
        title={unitId}
        icon={<MapPin size={18} aria-hidden="true" />}
        sub={monthIndex == null
          ? `Everyone counted at this location in TY${year}.`
          : `Everyone counted at this location in ${MONTH_LABELS[monthIndex]}, TY${year}.`}
        actions={(
          <>
            {/* Method is a CHOICE the statute has not made. A page reached by a
                link that carried one reading must still offer the other. */}
            {onChangeMethod ? <MethodTabs method={method} onChange={onChangeMethod} /> : null}
            {month != null ? (
              <button type="button" className="btn btn-secondary" onClick={() => onChangeMonth?.(null)}>
                Show the whole year
              </button>
            ) : null}
          </>
        )}
      />

      {loading && !payload ? (
        <div className="panel trend-loading"><Loader2 size={16} className="spin" /> Reading the warehouse…</div>
      ) : null}
      {error ? <div className="callout warn">{error}</div> : null}

      {payload && !calculated ? (
        <div className="panel">
          <h2 className="panel-title">Awaiting the next run</h2>
          <p className="page-sub">
            {payload.message
              || 'This year has not been assessed yet. It carries no figure — not a zero.'}
          </p>
        </div>
      ) : null}

      {calculated ? (
        <>
          {/* 29 Sep: the stat cards below say these counts; the banner said
              them again. The run behind them is a note; the story is Copilot. */}
          <InsightBar
            notes={[provenanceLine(payload.run)]}
            request={{
              page: 'unit', clientId, taxYear: year, state, method, worksiteId: unitId, month,
            }}
          />

          <StatRow>
            <StatCard
              label={monthIndex == null ? 'Counted this year' : `Counted in ${MONTH_LABELS[monthIndex]}`}
              value={countedTotal}
              tone="accent"
            />
            {unit ? <StatCard label="Average headcount" value={fmtHeadcount(unit.average_headcount)} /> : null}
            {/* A labelled card with no value is worse than no card. */}
            {unit?.base_year != null ? <StatCard label="Base year" value={`TY${unit.base_year}`} /> : null}
            {unit?.status ? (
              <StatCard
                label="Reading"
                value={String(unit.status).replace(/_/g, ' ')}
                tone={unit.qualified ? 'good' : 'warn'}
              />
            ) : null}
            {/* Withheld rather than restated while that list is narrowed: a
                filtered cusp count is a different figure in the same words. */}
            <StatCard
              label={`Within ${BAND} hrs of the floor`}
              value={nearWire ? '—' : inBand.length}
              sub={nearWire
                ? 'a filter is narrowing that list'
                : (nearTotal ? `${nearTotal} ineligible in all` : null)}
              tone={!nearWire && inBand.length ? 'warn' : 'neutral'}
              empty={!nearTotal}
            />
          </StatRow>

          <div className="tcc-grid-tabbar">
            <GridTabs
              tabs={tabs}
              active={tab}
              onChange={(next) => patchSearch({ tab: next === 'people' ? '' : next })}
            />
            {floor != null ? (
              <span className="small muted">
                floor {floor} hrs / {MONEY.format(wageFloor)} a week
              </span>
            ) : null}
          </div>

          <GridTabPanel id="people" active={tab}>
            <section className="panel" id="unit-counted">
              <FilterBar
                specs={EMPLOYEE_COLUMNS}
                filters={empFilters}
                shown={employees.length}
                total={countedTotal}
                noun="employees"
                onClear={(column) => empFilter(column, '')}
              />
              {employees.length ? (
                <>
                  <div className="tcc-table-wrap">
                    <table className="tbl tbl-compact">
                      <thead>
                        <tr>
                          <Head col={EMPLOYEE_COLUMNS.employee_id} sort={sort} onSort={onSort} filters={empFilters} onFilter={empFilter} lead />
                          <Head col={EMPLOYEE_COLUMNS.weeks_worked} sort={sort} onSort={onSort} filters={empFilters} onFilter={empFilter} />
                          <th>Worked</th>
                          <Head col={EMPLOYEE_COLUMNS.total_hours} sort={sort} onSort={onSort} filters={empFilters} onFilter={empFilter} />
                          <Head col={EMPLOYEE_COLUMNS.avg_weekly_hours} sort={sort} onSort={onSort} filters={empFilters} onFilter={empFilter} />
                          <Head col={EMPLOYEE_COLUMNS.avg_weekly_wages} sort={sort} onSort={onSort} filters={empFilters} onFilter={empFilter} />
                          {showShare
                            ? <th className="num" title="Fraction of this employee allocated to this location">Share</th>
                            : null}
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {employees.slice(0, 300).map((person) => (
                          <tr key={person.record_token}>
                            <td className="cell-strong">{person.employee_id}</td>
                            <Count value={person.weeks_worked} decimals={1} />
                            <Window from={person.first_pps || person.first_start} to={person.last_ppe || person.last_end} />
                            <Count value={person.total_hours} decimals={1} />
                            <Effort value={person.avg_weekly_hours} floor={floor} />
                            <Effort value={person.avg_weekly_wages} floor={wageFloor} money />
                            {showShare
                              ? <td className="num">{person.weight == null ? '—' : num(person.weight).toFixed(2)}</td>
                              : null}
                            <td>
                              <button
                                type="button"
                                className="tcc-link"
                                onClick={() => onOpenEmployee?.(person.record_token)}
                              >
                                Open the walk
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {employees.length > 300 ? <p className="small muted">First 300 shown.</p> : null}
                </>
              ) : (
                <div className="callout info">
                  {empWire
                    ? 'No employee counted here matches that filter. Clear it to see the whole list.'
                    : 'Nobody was counted here. No pay period reached this month\u2019s measuring date.'}
                </div>
              )}
            </section>
          </GridTabPanel>

          {/* A separate cohort, never merged into the counted list. These
              employees did NOT qualify, and one table would say they did. */}
          <GridTabPanel id="near" active={tab}>
            <section className="panel tcc-near-panel" id="unit-near">
              <p className="page-sub">
                Nobody here counted toward the credit. The band is {BAND} hours, applied
                to the {floor}-hour floor this programme-year sets — so the top of this
                list is the shortest distance between this location and another job.
              </p>
              <FilterBar
                specs={EMPLOYEE_COLUMNS}
                filters={nearFilters}
                shown={near.length}
                total={nearTotal}
                noun="ineligible employees"
                onClear={(column) => nearFilter(column, '')}
              />
              {stackable || stack.entries.length ? (
                <StackBar
                  ticked={ticked.length}
                  onAddSelected={() => addToStack(ticked)}
                  stackSize={stack.entries.length}
                  onOpen={() => navigate(stack.openHref)}
                />
              ) : null}
              {near.length ? (
                <div className="tcc-table-wrap">
                  <table className="tbl tbl-compact">
                    <thead>
                      <tr>
                        {stackable ? (
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
                        <Head col={EMPLOYEE_COLUMNS.employee_id} sort={sort} onSort={onSort} filters={nearFilters} onFilter={nearFilter} lead />
                        <Head col={EMPLOYEE_COLUMNS.weeks_worked} sort={sort} onSort={onSort} filters={nearFilters} onFilter={nearFilter} />
                        <th>Worked</th>
                        <Head col={EMPLOYEE_COLUMNS.total_hours} sort={sort} onSort={onSort} filters={nearFilters} onFilter={nearFilter} />
                        <Head col={EMPLOYEE_COLUMNS.avg_weekly_hours} sort={sort} onSort={onSort} filters={nearFilters} onFilter={nearFilter} />
                        {/* Short by is FLOOR MINUS HOURS — the hours column read
                            backwards. A second control over one quantity is how
                            two filters end up disagreeing about one row. */}
                        <th className="num" title="Floor minus average weekly hours">Short by</th>
                        {/* The partner's question, per person. NOT the same number as
                            "short by": somebody clearing the hours floor and
                            failing the wage floor needs extra hours priced at
                            their own rate, and the binding requirement is the
                            larger of the two. */}
                        <th className="num" title="Additional hours a week that clear every failing floor, at this employee's own rate">
                          To qualify
                        </th>
                        <Head col={EMPLOYEE_COLUMNS.avg_weekly_wages} sort={sort} onSort={onSort} filters={nearFilters} onFilter={nearFilter} />
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {near.map((person) => {
                        const gap = floor == null ? null : floor - num(person.avg_weekly_hours);
                        const within = gap != null && gap <= BAND;
                        const entry = stackEntry(person);
                        const stacked = entry && stack.tokens.has(person.record_token);
                        return (
                          <tr key={person.record_token} className={stacked ? 'prox-stacked' : (within ? 'trend-amber' : undefined)}>
                            {stackable ? (
                              <td className="prox-tick">
                                {entry && !stacked ? (
                                  <input
                                    type="checkbox"
                                    aria-label={`Select ${person.employee_id}`}
                                    checked={selected.has(person.record_token)}
                                    onChange={() => toggle(person.record_token)}
                                  />
                                ) : null}
                              </td>
                            ) : null}
                            <td className="cell-strong">
                              {/* The id opens the walk: a separate "Walk" column
                                  pushed the stack control off the page at 1024. */}
                              <button
                                type="button"
                                className="tcc-link"
                                title="Open this employee's calculation walk"
                                aria-label={`Open the walk for ${person.employee_id}`}
                                onClick={() => onOpenEmployee?.(person.record_token)}
                              >
                                {person.employee_id}
                              </button>
                            </td>
                            <Count value={person.weeks_worked} decimals={1} />
                            <Window from={person.first_start} to={person.last_end} />
                            <Count value={person.total_hours} decimals={1} />
                            <td className="num">{num(person.avg_weekly_hours).toFixed(2)}</td>
                            <td className="num">
                              {/* A NEGATIVE gap is not a shortfall. The cohort
                                  is everyone ineligible at this unit, which
                                  includes people over the hours floor who fail
                                  on wages — 192 of 200 at one Candle Bottle
                                  unit — and "short by -1.33 hrs" in an amber
                                  pill reads as a shortfall that is not there.
                                  Their real distance is the next column. */}
                              {gap == null ? '—' : gap <= 0 ? (
                                <span className="muted" title="Already over the hours floor; the wage floor is what fails">
                                  over
                                </span>
                              ) : (
                                <span className={within ? 'pill pill-warn' : 'muted'}>
                                  {gap.toFixed(2)} hrs
                                </span>
                              )}
                            </td>
                            <Lever person={person} hoursGap={gap} />
                            <td className="num">{MONEY.format(num(person.avg_weekly_wages))}</td>
                            <td className="tcc-row-actions">
                              {stacked ? (
                                <button
                                  type="button"
                                  className="btn btn-secondary prox-whatif on"
                                  onClick={() => stack.remove(person.record_token)}
                                  aria-label={`Remove ${person.employee_id} from the What-if stack`}
                                  title="In the What-if stack — click to remove"
                                >
                                  <Check size={13} aria-hidden="true" />
                                </button>
                              ) : entry ? (
                                <button
                                  type="button"
                                  className="btn btn-secondary prox-whatif"
                                  disabled={stack.entries.length >= MAX_STACK}
                                  onClick={() => addToStack([person])}
                                  aria-label={`Add ${person.employee_id} to the What-if stack`}
                                  title={entry.raise
                                    ? `Pre-filled: +${entry.hours} hrs/wk and a $${entry.raise.toFixed(2)}/hr raise for the rest of the year`
                                    : `Pre-filled: +${entry.hours} hrs/wk for the rest of the year`}
                                >
                                  <Plus size={13} aria-hidden="true" />
                                </button>
                              ) : null}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                  <p className="small muted">
                    <b>To qualify</b> is the additional hours a week that would
                    clear every floor this person fails, priced at their own
                    rate — so it exceeds <b>Short by</b> wherever the wage floor
                    is the binding one (marked <sup>†</sup>). A lever marked
                    <sup>*</sup> needs a week nobody works. No dollar figure is
                    shown per person: a location's credit turns on its job count
                    against a threshold, so the marginal employee is worth the
                    whole tranche or nothing, and neither can be attributed to a
                    row.
                  </p>
                </div>
              ) : (
                <div className="callout info">
                  {nearWire
                    ? 'Nobody ineligible here matches that filter.'
                    : 'Everybody with payroll at this location counted toward the credit.'}
                </div>
              )}
            </section>
          </GridTabPanel>
        </>
      ) : null}
    </div>
  );
}

/** Effort against a floor, marked where it falls short. */
function Effort({ value, floor, money = false }) {
  if (value == null) return <td className="num muted">—</td>;
  const n = num(value);
  const short = floor != null && n < floor;
  return (
    <td className={`num${short ? ' tone-warn' : ''}`}>
      {money ? MONEY.format(n) : n.toFixed(2)}
    </td>
  );
}

/**
 * "How many additional hours per week would Sally need to work?"
 *
 * The one figure the partner asks for by name, and deliberately NOT a dollar value.
 * A location's credit turns on its job count against a threshold, so the
 * marginal person is worth the whole tranche if they cross it and nothing at
 * all if they do not — there is no honest way to attribute that to a row. The
 * column says the hours.
 *
 * Bigger than "short by" whenever the wage floor is the binding one, which is
 * why the two columns sit next to each other rather than one replacing the
 * other. `failure_mode` names which floor is doing the work.
 */
function Lever({ person, hoursGap }) {
  const hours = person.additional_weekly_hours;
  if (hours == null) {
    // No weeks worked, or no rate to price the extra hours at. An employee we
    // cannot state a lever for is not an employee needing zero hours.
    return <td className="num muted" title="No rate on file to price additional hours at">—</td>;
  }
  // Marked from the COMPARISON, not from `failure_mode`. Somebody can fail both
  // floors and still have the hours gap bind — 31.23 hrs at $620.90 needs 3.77
  // more hours for the schedule and 0.76 for the pay — and marking them would
  // claim the wage floor moved a number it did not.
  const wageBound = hoursGap != null && num(hours) > hoursGap + 0.005;
  const title = [
    `${num(hours).toFixed(2)} more hours a week takes them to `
      + `${num(person.projected_weekly_hours).toFixed(2)}.`,
    wageBound ? 'The wage floor is binding, so this exceeds the hours gap alone.' : null,
    person.hourly_rate_to_qualify != null
      ? `Or leave the schedule alone and pay ${MONEY.format(num(person.hourly_rate_to_qualify))}/hr.`
      : null,
  ].filter(Boolean).join(' ');

  if (person.exceeds_plausible_week) {
    // A 90-hour week is not a lever. Saying so is the difference between a
    // work list and a list of impossibilities.
    return (
      <td className="num muted" title={`${title} That is not a plausible week.`}>
        {num(hours).toFixed(2)} hrs<sup>*</sup>
      </td>
    );
  }
  return (
    <td className="num" title={title}>
      <b>{num(hours).toFixed(2)} hrs</b>
      {/* NOT a `$`. This column carries no money, and a dollar sign in a
          numeric cell reads as one however it is marked up. */}
      {wageBound ? <sup title="Wage floor binding">†</sup> : null}
    </td>
  );
}

/** A measured quantity with no floor to read it against. */
function Count({ value, decimals = 0 }) {  if (value == null) return <td className="num muted">—</td>;
  // Weeks are FRACTIONAL in the warehouse — 50.86, not 51 — because a pay
  // period rarely ends on a week boundary. Rounding to whole weeks here would
  // present a derived figure as a count of something.
  return <td className="num">{num(value).toFixed(decimals)}</td>;
}

/**
 * Where in the year the weeks fell.
 *
 * Six weeks in January and six weeks spread across a year are different facts,
 * and a weekly average renders them identically.
 */
function Window({ from, to }) {
  const start = shortDate(from);
  const end = shortDate(to);
  if (!start && !end) return <td className="muted">—</td>;
  // One text node, not three: a range split across elements cannot be read as
  // a range by anything that queries the rendered text.
  return <td className="tcc-window">{`${start} \u2013 ${end}`}</td>;
}

/** A sortable, filterable column header. Both are server-side. */
function Head({ col, sort, onSort, filters, onFilter, lead = false }) {
  const active = sort.field === col.key;
  return (
    <th className={lead ? undefined : 'num'}>
      <button
        type="button"
        className={`th-sort${active ? ' active' : ''}`}
        aria-sort={active ? (sort.dir === 'desc' ? 'descending' : 'ascending') : 'none'}
        onClick={() => onSort(col.key)}
      >
        {col.label}
        {active ? <span aria-hidden="true">{sort.dir === 'desc' ? '\u25be' : '\u25b4'}</span> : null}
      </button>
      <ColumnFilter
        spec={col}
        value={filters[col.key] || ''}
        onChange={(expr) => onFilter(col.key, expr)}
      />
    </th>
  );
}
