import { useCallback, useEffect, useRef, useState } from 'react';
import { Loader2, TrendingUp } from 'lucide-react';
import { fetchClientUnits, simulateEmployees, simulateOneZero, simulateUnit } from '../api.js';
import { USD } from '../lib/coverage.js';
import { designationCode, designationTitle, pillClass, readingMeta } from '../lib/trendGrid.js';
import { ENUM, NUMERIC, TEXT } from '../lib/gridFilter.js';
import SortHeader from './SortHeader.jsx';
import { FilterBar } from './ColumnFilter.jsx';
import useTableControls from './useTableControls.js';
import StatCard, { StatRow } from './StatCard.jsx';

/**
 * What-If — what would change the answer.
 *
 * Four levers against the real One/Zero engine: hire, lose, hours, wages. A
 * projection is still a statutory figure — somebody will act on it — so it runs
 * under the same rules as an actual calculation and refuses a year with no
 * authored statute rather than borrowing a neighbour's.
 *
 * This file used to carry a second half: `PlanProximity`, the client-grain list
 * of who was closest to a threshold. That question is now a PriorityBand on the
 * book, where it sits beside the clients it was competing with for attention
 * rather than behind its own destination.
 */

const LEVERS = [
  {
    action: 'add_headcount',
    label: 'Hire',
    unit: 'roles',
    step: 1,
    initial: 5,
    hint: 'Adds employees in the role described. Left blank, each is full-time at the pattern of your highest-hours existing role.',
  },
  {
    action: 'remove_headcount',
    label: 'Lose',
    unit: 'roles',
    step: 1,
    initial: 5,
    hint: 'Removes the lowest-hours employees first — the ones nearest the floor.',
  },
  {
    action: 'adjust_hours',
    label: 'Hours',
    unit: 'hrs/week each',
    step: 1,
    initial: 2,
    hint: 'Shifts every employee\u2019s weekly hours. Moves people across the 35-hour test.',
  },
  {
    action: 'adjust_wages',
    label: 'Wages',
    unit: '% change',
    step: 1,
    initial: 5,
    hint: 'Shifts every employee\u2019s pay. Moves people across the weekly wage floor.',
  },
];

const num = (v) => (Number.isFinite(Number(v)) ? Number(v) : 0);

function Delta({ value, format = (v) => v, invert = false }) {
  const n = num(value);
  if (n === 0) return <span className="plan-delta flat">no change</span>;
  const good = invert ? n < 0 : n > 0;
  return (
    <span className={`plan-delta ${good ? 'up' : 'down'}`}>
      {n > 0 ? '+' : ''}{format(n)}
    </span>
  );
}

/** Pick a lever definition by its action, falling back to Hire. */
const leverFor = (action) => LEVERS.find((l) => l.action === action) || LEVERS[0];

/**
 * The client's locations for one year, for the location filter.
 *
 * Read from the grid's own endpoint so the menu offers exactly the locations
 * the grid shows — a location the run does not hold cannot be projected, and
 * offering it would read as a location with nothing to say.
 */
function useLocations(clientId, state, year, method) {
  const [locations, setLocations] = useState([]);
  useEffect(() => {
    let live = true;
    if (clientId == null || !state || year == null) { setLocations([]); return undefined; }
    fetchClientUnits(clientId, { state, method, year })
      .then((body) => {
        if (!live) return;
        const names = new Map((body?.units || []).map((u) => [u.worksite_id, u.name]));
        const ids = [...new Set((body?.items || []).map((item) => item.worksite_id))].sort();
        setLocations(ids.map((id) => ({ id, name: names.get(id) || id })));
      })
      .catch(() => { if (live) setLocations([]); });
    return () => { live = false; };
  }, [clientId, state, year, method]);
  return locations;
}

/**
 * The four levers, run against the statutory engine.
 *
 * Client-wide by default. With a location selected it runs `simulateUnit`,
 * which prices the projection the way the location grid prices it — against
 * that location's own frozen base year — so a what-if opened from a Reading
 * pill cannot disagree with the row that opened it.
 *
 * `whatIf` is the URL state (`lib/whatIf.parseWhatIf`). A pill that pre-fills a
 * lever and asks to run gets its answer on arrival. Editing the levers by hand
 * afterwards does not touch the URL, so it cannot re-seed them mid-keystroke.
 */
export function PlanLevers({
  scope, clientName, whatIf = null, onChangeUnit, stackContext = null, onChangeStack,
}) {
  if (whatIf?.stack?.length) {
    return (
      <EmployeeStack
        scope={scope}
        clientName={clientName}
        whatIf={whatIf}
        context={stackContext}
        onChangeStack={onChangeStack}
      />
    );
  }
  return <ClientLevers scope={scope} clientName={clientName} whatIf={whatIf} onChangeUnit={onChangeUnit} />;
}

const hrs2 = (v) => `${num(v).toFixed(2)}`;
const perHour = (v) => `$${num(v).toFixed(2)}`;

/** A designation, as the grid draws it — shown, not applied by the engine. */
function DesignationPill({ row, year }) {
  if (!row) return <span className="muted">—</span>;
  const withYear = { ...row, tax_year: year };
  const code = designationCode(withYear);
  return (
    <span className={`pill ${code === 'Unassigned' ? 'pill-neutral' : 'pill-accent'}`} title={designationTitle(withYear)}>
      {code}
    </span>
  );
}

/**
 * The Employee STACK (28 Sep; WI-19 was one employee). The partner: "In order to get
 * her over the hurdle for the remaining year, she has to work this many hours
 * per week." James: "select a few and stack them, so we can see the what-if
 * for a multi-employee modification."
 *
 * One row per employee, with where they work and what they earn today, and two
 * levers each — more hours a week and a raise in $/hr — pre-filled from Near
 * the line with whatever closes THAT person's gap. Project runs every change
 * together in one engine run; a sum of single-employee projections would miss
 * two people moving a location that neither could move alone.
 *
 * The stack's membership and starting figures live in the URL (`wstack`), so a
 * pasted link reproduces it. Edits are local until the next Project; removing
 * a row writes the remaining edits back so they survive.
 */
function EmployeeStack({ scope, clientName, whatIf, context, onChangeStack }) {
  const [entries, setEntries] = useState(whatIf.stack);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [running, setRunning] = useState(false);
  const state = scope.jurisdiction;
  const year = whatIf.year ?? scope.year;
  const method = whatIf.method || 'min_max';

  const run = useCallback(async (stack) => {
    if (!state || year == null || !stack.length) return;
    setRunning(true);
    setError(null);
    try {
      setResult(await simulateEmployees({
        clientId: scope.clientId, taxYear: year, state, method,
        employees: stack.map((e) => ({
          recordToken: e.token, additionalWeeklyHours: e.hours, hourlyRaise: e.raise,
        })),
      }));
    } catch (reason) {
      setError(String(reason));
      setResult(null);
    } finally {
      setRunning(false);
    }
  }, [scope.clientId, year, state, method]);

  // Re-seeded when the stack's MEMBERSHIP changes, not when a figure is typed.
  // `state` is in the key because a pasted link arrives before the scope has
  // resolved a jurisdiction: running then did nothing and the link was spent.
  const tokens = whatIf.stack.map((e) => e.token).join(',');
  const seedKey = [tokens, year, method, whatIf.autorun, state].join('|');
  const autoRan = useRef(null);
  useEffect(() => {
    setEntries(whatIf.stack);
    setResult(null);
    setError(null);
    if (whatIf.autorun && state && year != null && autoRan.current !== seedKey) {
      autoRan.current = seedKey;
      run(whatIf.stack);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seedKey]);

  // Sortable and filterable (29 Sep). The button still says how many are
  // projected, because a filter narrows what is SHOWN, never what is run.
  const byToken = new Map((result?.employees || []).map((e) => [e.record_token, e]));
  const described = entries.map((entry) => {
    const seen = context?.[entry.token];
    const got = byToken.get(entry.token);
    return {
      entry,
      seen,
      got,
      who: seen?.employee_id || got?.employee_id || `record ${entry.token.slice(0, 8)}…`,
      where: seen?.worksite_id || got?.worksite_id,
      designationRow: seen?.worksite_id ? seen : got,
      hours: seen?.avg_weekly_hours ?? got?.before?.avg_weekly_hours,
      wages: seen?.avg_weekly_wages ?? got?.before?.avg_weekly_wages,
      rate: seen?.implied_hourly_rate ?? got?.applied?.rate,
    };
  });
  const table = useTableControls(STACK_COLUMNS, described);

  if (!state) {
    return <div className="callout info">Select a single program so a projection has a statute to run under.</div>;
  }

  const edit = (token, field, value) => setEntries((prev) => prev.map((e) => (
    e.token === token ? { ...e, [field]: value } : e
  )));
  const remove = (token) => onChangeStack?.(entries.filter((e) => e.token !== token));

  return <>
    <section className="panel">
      <h3 className="panel-title">
        <span>What if {entries.length === 1 ? 'this employee works' : `these ${entries.length} employees work`} differently for the rest of the year …</span>
        <span className="right plan-scope">
          <span>{clientName} · {state} · TY{year} · {method === 'pay_period' ? 'Pay Period' : 'Min-Max'}</span>
          <span className="plan-unit-filter active"><span>Employees</span></span>
          {onChangeStack ? (
            <button type="button" className="plan-unit-clear" onClick={() => onChangeStack([])} aria-label="Clear the stack" title="Back to the client-wide levers">×</button>
          ) : null}
        </span>
      </h3>

      <FilterBar {...table.bar('employees')} />
      <div className="cov-scroll">
        <table className="cov-grid plan-table plan-stack">
          <thead>
            <tr>
              <SortHeader {...table.head('who')} className="cov-corner" />
              <SortHeader {...table.head('where')} />
              <SortHeader {...table.head('designation')} />
              <SortHeader {...table.head('hours')} className="num" />
              <SortHeader {...table.head('wages')} className="num" />
              <SortHeader {...table.head('rate')} className="num" />
              <SortHeader {...table.head('extra')} className="num" />
              <SortHeader {...table.head('raise')} className="num" />
              <th aria-label="Remove" />
            </tr>
          </thead>
          <tbody>
            {table.rows.map(({
              entry, who, where, designationRow, hours, wages, rate,
            }) => {
              return (
                <tr key={entry.token}>
                  <th scope="row" className="cov-rowhead mono">{who}</th>
                  <td>{where || '—'}</td>
                  <td><DesignationPill row={designationRow} year={year} /></td>
                  <td className="num">{hours == null ? '—' : hrs2(hours)}</td>
                  <td className="num">{wages == null ? '—' : USD.format(wages)}</td>
                  <td className="num">{rate == null ? '—' : perHour(rate)}</td>
                  <td className="num">
                    <input
                      type="number" min={0} max={40} step={0.25} value={entry.hours}
                      aria-label={`More hours a week for ${who}`}
                      onChange={(e) => edit(entry.token, 'hours', e.target.value)}
                    />
                  </td>
                  <td className="num">
                    <input
                      type="number" min={0} max={100} step={0.25} value={entry.raise}
                      aria-label={`Raise in dollars an hour for ${who}`}
                      onChange={(e) => edit(entry.token, 'raise', e.target.value)}
                    />
                  </td>
                  <td>
                    <button
                      type="button" className="plan-unit-clear" onClick={() => remove(entry.token)}
                      aria-label={`Remove ${who} from the stack`} title="Remove from the stack"
                    >×</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="plan-controls">
        <button className="btn btn-primary" disabled={running || !entries.length} onClick={() => run(entries)}>
          {running ? <Loader2 size={15} className="spin" /> : <TrendingUp size={15} />}
          {running ? 'Running…' : `Project ${entries.length === 1 ? '1 employee' : `all ${entries.length}`}`}
        </button>
      </div>
      <p className="small muted">
        Pre-filled from Near the line with what closes each person&apos;s gap: more hours
        where they are short on hours, and a raise where they are paid below the
        threshold rate. Periods already closed stay as paid; from the checkpoint on,
        each works their pace so far plus the extra, at their own rate plus the raise.
        Add more from How am I doing &rarr; Near the line.
      </p>
      {error && <div className="callout warn">{error}</div>}
    </section>

    {result ? <StackProjection result={result} year={year} /> : null}
  </>;
}

/** An open year's credit is not a figure yet; $0 would read as worthless. */
const NOT_PRICED_YET = (year) => `Not priced until TY${year} closes — nothing is claimable before then`;

const signedUsd = (v) => `${num(v) > 0 ? '+' : num(v) < 0 ? '−' : ''}${USD.format(Math.abs(num(v)))}`;

/**
 * The answer a What-if exists to give: the credit the change makes available.
 *
 * A closed year is priced by the engine. An open year is not claimable, so its
 * figure is the one labelled estimate the product makes — the year priced as if
 * it closed at its pace so far — and the card says so in its label, not in a
 * footnote a reader may not reach.
 */
export function CreditGained({ year, closed, runRate, extra = null }) {
  const estimate = !closed && runRate;
  const delta = closed ? closed.delta : runRate?.delta;
  const priced = closed || runRate;
  return (
    <StatRow>
      <StatCard
        label={estimate ? `Credit gained · TY${year} run-rate` : `Credit gained · TY${year}`}
        value={signedUsd(delta)}
        tone={num(delta) > 0 ? 'good' : num(delta) < 0 ? 'bad' : 'neutral'}
        empty={!priced}
        sub={priced
          ? (estimate
            ? `Estimate if TY${year} closes at this pace — not claimable until it does`
            : 'Annual credit, as the grid prices it')
          : NOT_PRICED_YET(year)}
      />
      {priced && priced.before != null ? (
        <StatCard
          label={estimate ? 'Run-rate before → after' : 'Annual credit before → after'}
          value={`${USD.format(num(priced.before))} → ${USD.format(num(priced.after))}`}
          sub={estimate
            ? (priced.locations != null
              ? `Across the ${priced.locations} location${priced.locations === 1 ? '' : 's'} the stack touches, each against its own base`
              : 'Priced against the location\u2019s own base')
            : `TY${year}`}
        />
      ) : null}
      {extra}
    </StatRow>
  );
}

function Verdict({ eligible }) {
  return eligible
    ? <span className="pill pill-ok">Eligible</span>
    : <span className="pill pill-bad">Not eligible</span>;
}

/** What changed, per person, in the words a reader repeats. */
function changeText(applied) {
  if (!applied) return '—';
  const parts = [];
  if (num(applied.projected_weekly_hours) !== num(applied.pace_weekly_hours)) {
    parts.push(`${hrs2(applied.pace_weekly_hours)} → ${hrs2(applied.projected_weekly_hours)} hrs/wk`);
  }
  if (num(applied.projected_rate) !== num(applied.rate)) {
    parts.push(`${perHour(applied.rate)} → ${perHour(applied.projected_rate)}/hr`);
  }
  return parts.length ? parts.join(' · ') : 'no change';
}

function StackProjection({ result, year }) {
  const { employees, locations, client, summary } = result;
  const people = useTableControls(PROJECTED_PEOPLE, employees);
  const places = useTableControls(PROJECTED_PLACES, locations);
  const open = locations.some((loc) => loc.in_progress);
  const creditDelta = client.annual_credit_usd_delta;
  const headline = [
    `${summary.became_eligible} of ${summary.employees} become eligible`,
    summary.lost_eligibility ? `${summary.lost_eligibility} lose eligibility` : null,
    `${summary.locations_moved} location${summary.locations_moved === 1 ? ' changes' : 's change'} reading`,
  ].filter(Boolean).join(' · ');
  const runRate = client.run_rate ? {
    delta: client.run_rate.delta_usd,
    before: client.run_rate.before_usd,
    after: client.run_rate.after_usd,
    locations: client.run_rate.locations,
  } : null;
  const closed = open ? null : {
    delta: creditDelta, before: client.annual_credit_usd_before, after: client.annual_credit_usd_after,
  };
  return (
    <section className="panel">
      <h3 className="panel-title">
        <span>Projection · {summary.employees} employee{summary.employees === 1 ? '' : 's'}</span>
        <span className="right">from {result.scope.as_of}</span>
      </h3>
      <CreditGained year={year} closed={closed} runRate={runRate} />
      <p className="plan-stack-answer">{headline}.</p>
      <FilterBar {...people.bar('employees')} />
      <div className="cov-scroll">
        <table className="cov-grid plan-table">
          <thead>
            <tr>
              <SortHeader {...people.head('employee')} className="cov-corner" />
              <SortHeader {...people.head('location')} />
              <SortHeader {...people.head('change')} />
              <SortHeader {...people.head('today')} />
              <SortHeader {...people.head('projected')} />
            </tr>
          </thead>
          <tbody>
            {people.rows.map((e) => (
              <tr key={e.record_token}>
                <th scope="row" className="cov-rowhead mono">{e.employee_id}</th>
                <td>{e.worksite_id || '—'} <DesignationPill row={e} year={year} /></td>
                <td>{changeText(e.applied)}</td>
                <td><Verdict eligible={e.before.eligible} /></td>
                <td><Verdict eligible={e.after.eligible} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {locations.length ? (
        <>
        <FilterBar {...places.bar('locations')} />
        <div className="cov-scroll">
          <table className="cov-grid plan-table">
            <thead>
              <tr>
                <SortHeader {...places.head('location')} className="cov-corner" />
                <SortHeader {...places.head('today')} />
                <SortHeader {...places.head('projected')} />
                <SortHeader {...places.head('change')} className="cov-total" />
              </tr>
            </thead>
            <tbody>
              {places.rows.map((loc) => {
                const was = readingMeta({ status: loc.in_progress ? 'in_progress' : (loc.before.qualified ? 'above_minimum' : 'below_minimum'), qualified: loc.before.qualified });
                const now = readingMeta({ status: loc.in_progress ? 'in_progress' : (loc.after.qualified ? 'above_minimum' : 'below_minimum'), qualified: loc.after.qualified });
                return [
                  <tr key={`${loc.worksite_id}-r`}>
                    <th scope="row" className="cov-rowhead">
                      {loc.worksite_id} <DesignationPill row={loc} year={year} /> · against its {loc.threshold}-job minimum
                    </th>
                    <td><span className={`pill ${pillClass(was.tone)}`}>{was.label}</span> {marginText(loc.before.jobs_margin)}</td>
                    <td><span className={`pill ${pillClass(now.tone)}`}>{now.label}</span> {marginText(loc.after.jobs_margin)}</td>
                    <td className="cov-total"><Delta value={loc.after.average_headcount - loc.before.average_headcount} format={(v) => `${v.toFixed(2)} avg`} /></td>
                  </tr>,
                  loc.in_progress && loc.run_rate ? (
                    <tr key={`${loc.worksite_id}-c`}>
                      <th scope="row" className="cov-rowhead">{loc.worksite_id} · annual credit, run-rate est.</th>
                      <td>{USD.format(loc.run_rate.before_usd)}</td>
                      <td>{USD.format(loc.run_rate.after_usd)}</td>
                      <td className="cov-total"><Delta value={loc.run_rate.delta_usd} format={(v) => USD.format(v)} /></td>
                    </tr>
                  ) : loc.in_progress ? (
                    <tr key={`${loc.worksite_id}-c`}>
                      <th scope="row" className="cov-rowhead">{loc.worksite_id} · annual credit</th>
                      <td colSpan={3} className="muted">{NOT_PRICED_YET(year)}</td>
                    </tr>
                  ) : (
                    <tr key={`${loc.worksite_id}-c`}>
                      <th scope="row" className="cov-rowhead">{loc.worksite_id} · annual credit</th>
                      <td>{USD.format(loc.before.annual_credit_usd)}</td>
                      <td>{USD.format(loc.after.annual_credit_usd)}</td>
                      <td className="cov-total"><Delta value={loc.after.annual_credit_usd - loc.before.annual_credit_usd} format={(v) => USD.format(v)} /></td>
                    </tr>
                  ),
                ];
              })}
              {open ? null : (
                <tr>
                  <th scope="row" className="cov-rowhead">Client annual credit, TY{year}</th>
                  <td>{USD.format(client.annual_credit_usd_before)}</td>
                  <td>{USD.format(client.annual_credit_usd_after)}</td>
                  <td className="cov-total"><Delta value={client.annual_credit_usd_delta} format={(v) => USD.format(v)} /></td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        </>
      ) : null}
      <p className="small muted">{result.method_note}</p>
    </section>
  );
}

/** The stack's columns, over the described rows `EmployeeStack` builds. */
const STACK_COLUMNS = {
  who: { key: 'who', label: 'Employee', type: TEXT, read: (r) => r.who },
  where: { key: 'where', label: 'Location', type: ENUM, read: (r) => r.where },
  designation: {
    key: 'designation', label: 'Designation', type: ENUM,
    read: (r) => (r.designationRow ? designationCode(r.designationRow) : ''),
  },
  hours: { key: 'hours', label: 'Hrs/wk', type: NUMERIC, read: (r) => r.hours },
  wages: { key: 'wages', label: '$/wk', type: NUMERIC, read: (r) => r.wages },
  rate: { key: 'rate', label: 'Rate', type: NUMERIC, read: (r) => r.rate },
  extra: { key: 'extra', label: '+ hrs/wk', type: NUMERIC, read: (r) => r.entry.hours },
  raise: { key: 'raise', label: '+ $/hr', type: NUMERIC, read: (r) => r.entry.raise },
};

const verdictWord = (eligible) => (eligible ? 'Eligible' : 'Not eligible');

const PROJECTED_PEOPLE = {
  employee: { key: 'employee', label: 'Employee', type: TEXT, read: (e) => e.employee_id },
  location: { key: 'location', label: 'Location', type: ENUM, read: (e) => e.worksite_id },
  change: { key: 'change', label: 'Rest of year', type: TEXT, read: (e) => changeText(e.applied) },
  today: { key: 'today', label: 'Today', type: ENUM, read: (e) => verdictWord(e.before.eligible) },
  projected: { key: 'projected', label: 'Projected', type: ENUM, read: (e) => verdictWord(e.after.eligible) },
};

const PROJECTED_PLACES = {
  location: { key: 'location', label: 'Location', type: TEXT, read: (l) => l.worksite_id },
  today: {
    key: 'today', label: 'Today', type: NUMERIC, read: (l) => l.before.jobs_margin, filterable: false,
  },
  projected: {
    key: 'projected', label: 'Projected', type: NUMERIC, read: (l) => l.after.jobs_margin, filterable: false,
  },
  change: {
    key: 'change', label: 'Change', type: NUMERIC,
    read: (l) => l.after.average_headcount - l.before.average_headcount,
  },
};
/** Hire, Lose, Hours, Wages — for the client, or for one location. */
function ClientLevers({ scope, clientName, whatIf = null, onChangeUnit }) {
  const [lever, setLever] = useState(leverFor(whatIf?.action));
  // WI-22. What the hired role IS. Blank means a full-time role clear of both
  // floors, which is what Hire always meant.
  const [hireHours, setHireHours] = useState('');
  const [hireRate, setHireRate] = useState('');
  const [magnitude, setMagnitude] = useState(whatIf?.magnitude ?? leverFor(whatIf?.action).initial);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [running, setRunning] = useState(false);

  // The state comes from the scope's derived jurisdiction. A what-if is a
  // statutory calculation, so it needs a programme-year it can be priced under.
  const state = scope.jurisdiction;
  const year = whatIf?.year ?? scope.year;
  const unitId = whatIf?.unitId || null;
  const method = whatIf?.method || 'min_max';
  const locations = useLocations(scope.clientId, state, year, method);
  const unitName = locations.find((l) => l.id === unitId)?.name;

  const run = useCallback(async (action, amount) => {
    if (!state || year == null) return;
    setRunning(true);
    setError(null);
    const role = action === 'add_headcount' ? {
      hours: hireHours === '' ? null : Number(hireHours),
      rate: hireRate === '' ? null : Number(hireRate),
    } : { hours: null, rate: null };
    try {
      setResult(unitId
        ? await simulateUnit({
          clientId: scope.clientId, worksiteId: unitId, taxYear: year,
          state, method, action, magnitude: Number(amount),
          hireWeeklyHours: role.hours, hireHourlyRate: role.rate,
        })
        : await simulateOneZero({
          client_id: scope.clientId,
          state,
          tax_year: year,
          action,
          magnitude: Number(amount),
          ...(role.hours != null ? { hire_weekly_hours: role.hours } : {}),
          ...(role.rate != null ? { hire_hourly_rate: role.rate } : {}),
        }));
    } catch (reason) {
      setError(String(reason));
      setResult(null);
    } finally {
      setRunning(false);
    }
  }, [scope.clientId, state, year, unitId, method, hireHours, hireRate]);

  // Arriving from a pill, or the URL changing under the panel, re-seeds the
  // levers. Keyed on the values, not the object, so a re-render does not
  // re-run a projection nobody asked for again.
  // `state` is in the key for the reason given on the employee lever above.
  const seedKey = [unitId, year, method, whatIf?.action, whatIf?.magnitude, whatIf?.autorun, state].join('|');
  const autoRan = useRef(null);
  useEffect(() => {
    const seeded = leverFor(whatIf?.action);
    const amount = whatIf?.magnitude ?? seeded.initial;
    setLever(seeded);
    setMagnitude(amount);
    setResult(null);
    setError(null);
    // Once per link. StrictMode runs this effect twice in development, and a
    // projection costs an engine run.
    if (whatIf?.autorun && state && year != null && autoRan.current !== seedKey) {
      autoRan.current = seedKey;
      run(seeded.action, amount);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seedKey]);

  if (!state) {
    return (
      <div className="callout info">
        Select a single program so a projection has a jurisdiction and a statute
        to run under.
      </div>
    );
  }

  const baseline = result?.baseline;
  const projected = result?.projected;
  const unitResult = result && result.scope?.worksite_id;

  return <>
    <section className="panel">
      <h3 className="panel-title">
        <span>What if {clientName}{unitId ? ` at ${unitName || unitId}` : ''} …</span>
        <span className="right plan-scope">
          <span>{state} · TY{year}{unitId ? ` · ${method === 'pay_period' ? 'Pay Period' : 'Min-Max'}` : ''}</span>
          <label className={`plan-unit-filter${unitId ? ' active' : ''}`}>
            <span>Location</span>
            <select
              value={unitId || ''}
              onChange={(event) => onChangeUnit?.(event.target.value || null)}
              disabled={!onChangeUnit || !locations.length}
              aria-label="Filter the what-if to one location"
            >
              <option value="">All locations</option>
              {locations.map((l) => (
                <option key={l.id} value={l.id}>{l.name === l.id ? l.id : `${l.name} · ${l.id}`}</option>
              ))}
              {unitId && !locations.some((l) => l.id === unitId)
                ? <option value={unitId}>{unitId}</option>
                : null}
            </select>
          </label>
          {unitId && onChangeUnit ? (
            <button
              type="button"
              className="plan-unit-clear"
              onClick={() => onChangeUnit(null)}
              aria-label={`Clear the ${unitId} filter`}
              title="Back to the whole client"
            >
              ×
            </button>
          ) : null}
        </span>
      </h3>

      <div className="plan-levers">
        {LEVERS.map((l) => (
          <button
            key={l.action}
            type="button"
            className={`plan-lever ${lever.action === l.action ? 'active' : ''}`}
            onClick={() => { setLever(l); setMagnitude(l.initial); setResult(null); }}
          >
            {l.label}
          </button>
        ))}
      </div>

      <div className="plan-controls">
        <label>
          <input
            type="number"
            value={magnitude}
            step={lever.step}
            aria-label={`${lever.label} amount`}
            onChange={(e) => setMagnitude(e.target.value)}
          />
          <span>{lever.unit}{unitId ? ` at ${unitId}` : ''}</span>
        </label>
        {lever.action === 'add_headcount' ? (
          <span className="plan-role">
            <label>
              <input
                type="number" min={1} max={80} step={1} value={hireHours} placeholder="40"
                aria-label="Hours a week for each hire"
                onChange={(e) => { setHireHours(e.target.value); setResult(null); }}
              />
              <span>hrs/week</span>
            </label>
            <label>
              <span>at $</span>
              <input
                type="number" min={1} max={500} step={0.25} value={hireRate} placeholder="auto"
                aria-label="Hourly pay for each hire"
                onChange={(e) => { setHireRate(e.target.value); setResult(null); }}
              />
              <span>/hr</span>
            </label>
          </span>
        ) : null}
        <button className="btn btn-primary" disabled={running} onClick={() => run(lever.action, magnitude)}>
          {running ? <Loader2 size={15} className="spin" /> : <TrendingUp size={15} />}
          {running ? 'Running…' : 'Project'}
        </button>
      </div>
      <p className="small muted">
        {lever.hint}
        {lever.action === 'add_headcount'
          ? ' A part-time or low-paid role is projected as it is: the engine does not count it, and the projection says why.'
          : ''}
      </p>

      {/* The first question anybody asks a what-if screen. */}
      <div className="callout info">
        <b>Nothing here is a stored scenario.</b> The four levers are fixed
        choices; the answer is not. Each run mutates this client&apos;s real
        payroll rows in memory and re-runs the same monthly employment engine that produced
        the certified figures, under {state} statute for TY{year}. A year with no
        authored rule pack is refused rather than estimated — which is why a
        projection is allowed to inform a filing decision at all.
      </div>

      {error && <div className="callout warn">{error}</div>}
    </section>

    {unitResult ? <UnitProjection result={result} year={year} /> : null}

    {result && !unitResult && (
      <section className="panel">
        <h3 className="panel-title">
          <span>Projection</span>
          <span className="right">{result.detail}</span>
        </h3>
        <CreditGained
          year={year}
          closed={{
            delta: result.delta.annual_credit_usd,
            before: baseline.annual_credit_usd,
            after: projected.annual_credit_usd,
          }}
        />
        <div className="cov-scroll">
          <table className="cov-grid plan-table">
            <thead>
              <tr>
                <th className="cov-corner">Measure</th>
                <th>Today</th>
                <th>Projected</th>
                <th className="cov-total">Change</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <th scope="row" className="cov-rowhead">Average headcount</th>
                <td>{baseline.average_headcount}</td>
                <td>{projected.average_headcount}</td>
                <td className="cov-total"><Delta value={result.delta.average_headcount} /></td>
              </tr>
              <tr>
                <th scope="row" className="cov-rowhead">Employees passing both tests</th>
                <td>{baseline.eligible_employee_count}</td>
                <td>{projected.eligible_employee_count}</td>
                <td className="cov-total"><Delta value={result.delta.eligible_employee_count} /></td>
              </tr>
              <tr>
                <th scope="row" className="cov-rowhead">Annual credit</th>
                <td>{USD.format(baseline.annual_credit_usd)}</td>
                <td>{USD.format(projected.annual_credit_usd)}</td>
                <td className="cov-total">
                  <Delta value={result.delta.annual_credit_usd} format={(v) => USD.format(v)} />
                </td>
              </tr>
              <tr>
                <th scope="row" className="cov-rowhead">Lifetime credit</th>
                <td>{USD.format(baseline.lifetime_credit_usd)}</td>
                <td>{USD.format(projected.lifetime_credit_usd)}</td>
                <td className="cov-total">
                  <Delta value={result.delta.lifetime_credit_usd} format={(v) => USD.format(v)} />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="small muted">
          Run against the same engine that produces the filed figure, under{' '}
          {result.eligibility_floors.min_weekly_hours} hours and{' '}
          {USD.format(result.eligibility_floors.min_weekly_wages)} per week — TY{year}&apos;s
          statute, not this year&apos;s. A projection is not a filing, but it is
          not a guess either.
        </p>
      </section>
    )}
  </>;
}

/** How far over or under the minimum, in words a reader repeats. */
function marginText(margin) {
  const n = num(margin);
  if (Math.abs(n) < 0.005) return 'exactly at the minimum';
  return n < 0 ? `${Math.abs(n).toFixed(2)} short` : `${n.toFixed(2)} over`;
}

/**
 * Today against projected at ONE location, in the grid's own vocabulary:
 * average, net new against its frozen base, the Reading, and the credit.
 */
function UnitProjection({ result, year }) {
  const { baseline, projected, delta } = result;
  const before = readingMeta(baseline);
  const after = readingMeta(projected);
  const [first, last] = result.series_years || [];
  return (
    <section className="panel">
      <h3 className="panel-title">
        <span>Projection · {result.scope.worksite_id}</span>
        <span className="right">{result.detail}</span>
      </h3>
      <CreditGained
        year={year}
        closed={result.open_year ? null : {
          delta: delta.annual_credit_usd, before: baseline.annual_credit_usd, after: projected.annual_credit_usd,
        }}
        runRate={result.run_rate ? {
          delta: result.run_rate.delta_usd, before: result.run_rate.before_usd, after: result.run_rate.after_usd,
        } : null}
      />
      <div className="cov-scroll">
        <table className="cov-grid plan-table">
          <thead>
            <tr>
              <th className="cov-corner">Measure</th>
              <th>Today</th>
              <th>Projected</th>
              <th className="cov-total">Change</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row" className="cov-rowhead">Average headcount</th>
              <td>{baseline.average_headcount}</td>
              <td>{projected.average_headcount}</td>
              <td className="cov-total"><Delta value={delta.average_headcount} /></td>
            </tr>
            <tr>
              <th scope="row" className="cov-rowhead">Net new vs TY{result.base_year} base</th>
              <td>{baseline.net_new_vs_base}</td>
              <td>{projected.net_new_vs_base}</td>
              <td className="cov-total"><Delta value={delta.net_new_vs_base} /></td>
            </tr>
            <tr>
              <th scope="row" className="cov-rowhead">Against the {baseline.threshold}-job minimum</th>
              <td>{marginText(baseline.jobs_margin)}</td>
              <td>{marginText(projected.jobs_margin)}</td>
              <td className="cov-total" />
            </tr>
            <tr>
              <th scope="row" className="cov-rowhead">Reading</th>
              <td><span className={`pill ${pillClass(before.tone)}`}>{before.label}</span></td>
              <td><span className={`pill ${pillClass(after.tone)}`}>{after.label}</span></td>
              <td className="cov-total" />
            </tr>
            <tr>
              <th scope="row" className="cov-rowhead">
                Annual credit, TY{year}{result.open_year && result.run_rate ? ' · run-rate est.' : ''}
              </th>
              {result.open_year && result.run_rate ? (
                <>
                  <td>{USD.format(result.run_rate.before_usd)}</td>
                  <td>{USD.format(result.run_rate.after_usd)}</td>
                  <td className="cov-total">
                    <Delta value={result.run_rate.delta_usd} format={(v) => USD.format(v)} />
                  </td>
                </>
              ) : result.open_year ? (
                <td colSpan={3} className="muted">{NOT_PRICED_YET(year)}</td>
              ) : (
                <>
                  <td>{USD.format(baseline.annual_credit_usd)}</td>
                  <td>{USD.format(projected.annual_credit_usd)}</td>
                  <td className="cov-total">
                    <Delta value={delta.annual_credit_usd} format={(v) => USD.format(v)} />
                  </td>
                </>
              )}
            </tr>
            {first != null ? (
              <tr>
                <th scope="row" className="cov-rowhead">Credit, TY{first}–TY{last}</th>
                <td>{USD.format(baseline.series_credit_usd)}</td>
                <td>{USD.format(projected.series_credit_usd)}</td>
                <td className="cov-total">
                  <Delta value={delta.series_credit_usd} format={(v) => USD.format(v)} />
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
      {result.open_year ? (
        <p className="callout info" role="note">{result.open_year.note}</p>
      ) : null}
      <p className="small muted">
        {result.method_note} Floors {result.eligibility_floors.min_weekly_hours} hours
        and {USD.format(result.eligibility_floors.min_weekly_wages)} per week.
      </p>
    </section>
  );
}

/**
 * Which jurisdiction a what-if runs under.
 *
 * Derived from the programme, never selected — the same rule the scope bar
 * follows. A projection needs exactly one.
 */
export function planJurisdiction(scope, scopeOptions) {
  const one = (scopeOptions?.programs || [])
    .find((p) => p.program_code === scope?.programCode);
  return one?.jurisdiction?.code || null;
}
