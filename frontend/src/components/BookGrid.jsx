import { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowRight, ChevronDown, ChevronRight, Loader2, MessageSquare } from 'lucide-react';
import { fetchClientCoverage } from '../api.js';
import { ColumnFilter, FilterBar } from './ColumnFilter.jsx';
import FootprintMap from './FootprintMap.jsx';
import SortHeader from './SortHeader.jsx';
import {
  ENUM, NUMERIC, TEXT, applyFilters, presentValues,
} from '../lib/gridFilter.js';
import { ranksByValue } from '../lib/bookSort.js';
import { money } from '../lib/coverage.js';
import { band, marginReading, trendReading } from '../lib/priority.js';

/**
 * The book — every client, ranked by why you would call them.
 *
 * Replaces the two tabs it grew out of. "Who to call" was a filtered subset of
 * this same data: `/api/claims/proximity` reads the identical claims and keeps
 * only cells within one job of a threshold. Making it a separate destination
 * meant the reader had to know which tab held the answer before they knew what
 * the answer was.
 *
 * ONE ROW PER CLIENT, showing that client's most actionable cell — which is
 * what `/api/v2/portfolio` has always returned. Expanding lazily loads the rest
 * of their programme-years, so "which programmes, which years" is one click
 * rather than a second screen.
 *
 * Ranked by PRIORITY BAND, not by dollar value. A client one hire from a
 * threshold is worth $0 today, the same $0 as one fifty hires short, so a value
 * sort buries exactly the client worth ringing. The band is computed
 * server-side so that sorting and paging cannot disagree with it.
 */

const COLUMNS = {
  client: { key: 'client', label: 'Client', type: TEXT, read: (r) => r.client_name || `Account ${r.client_id}` },
  // WI-20. Display-only: it changes no figure until the engine applies it.
  industry: { key: 'industry', label: 'Industry', type: ENUM, read: (r) => r.industry || 'Not recorded' },
  band: { key: 'band', label: 'Targeting', type: ENUM, read: (r) => r.priority_band },
  program: { key: 'program', label: 'Program', type: ENUM, read: (r) => r.program_code },
  year: { key: 'year', label: 'Year', type: NUMERIC, read: (r) => r.tax_year },
  identified: { key: 'identified', label: 'Identified', type: NUMERIC, read: (r) => Number(r.identified_usd ?? NaN) },
  margin: { key: 'margin', label: 'Margin', type: NUMERIC, read: (r) => r.jobs_margin },
  // The map writes into THIS, through the same grammar every other column
  // uses. A parallel selection mechanism is how a map and a filter bar end up
  // disagreeing about which clients are on screen.
  state: { key: 'state', label: 'State', type: ENUM, multi: true, read: (r) => r.states || [] },
};

const SPECS = Object.fromEntries(Object.values(COLUMNS).map((c) => [c.key, c]));

function BandChip({ id }) {
  const meta = band(id);
  return (
    <span className={`tcc-band tcc-band-${meta.tone}`} title={meta.why || meta.line}>
      {meta.label}
    </span>
  );
}

/**
 * The band, plus the reading it moves in.
 *
 * An `on_the_line` client rendered in dollars reads as worthless, because today
 * they are — jobs is the number that changes. Everything else moves in dollars,
 * and the Identified column already says that, so repeating it here was one
 * figure in two places.
 */
function BandCell({ row }) {
  const meta = band(row.priority_band);
  const jobs = row.priority_band === 'on_the_line' ? marginReading(row.jobs_margin) : null;
  return (
    <td>
      <span className={`tcc-band tcc-band-${meta.tone}`} title={meta.why || meta.line}>
        {meta.label}
      </span>
      {jobs ? <span className={`tcc-band-note tcc-margin-${jobs.tone}`}>{jobs.text}</span> : null}
    </td>
  );
}

function ExpandedCells({ clientId }) {
  const [state, setState] = useState({ loading: true, cells: null, error: null });

  useEffect(() => {
    let cancelled = false;
    setState({ loading: true, cells: null, error: null });
    // Every year, because the book is not year-scoped. Expanding a row is where
    // "which programmes, which years" is answered.
    fetchClientCoverage(clientId, {})
      .then((body) => {
        if (!cancelled) setState({ loading: false, cells: body?.cells || [], error: null });
      })
      .catch((e) => { if (!cancelled) setState({ loading: false, cells: null, error: e.message }); });
    return () => { cancelled = true; };
  }, [clientId]);

  if (state.loading) {
    return <div className="tcc-expand-note"><Loader2 size={14} className="spin" /> Reading the rest of the book…</div>;
  }
  if (state.error) return <div className="tcc-expand-note callout warn">{state.error}</div>;
  if (!state.cells?.length) {
    return (
      <div className="tcc-expand-note muted">
        No other programme-years recorded for this client. That is not a zero —
        nothing else has been assessed.
      </div>
    );
  }

  return (
    <table className="tbl-compact tcc-expand-table">
      <thead>
        {/* Claimed and Outcome are gone for the same reason the parent's
            Recoverable and Exposure columns are. `outcome` reads
            `over_claimed` / `unclaimed` / `correctly_not_claimed` — every one
            of those asserts something about a filing we do not hold. The band
            already carries the reading we CAN stand behind. */}
        <tr>
          <th>Band</th><th>Program</th><th>Year</th>
          <th className="num">Identified</th><th className="num">Margin</th>
        </tr>
      </thead>
      <tbody>
        {state.cells.map((cell) => {
          const reading = marginReading(cell.jobs_margin);
          return (
            <tr key={`${cell.program_code}-${cell.tax_year}`}>
              <td><BandChip id={cell.priority_band} /></td>
              <td>{cell.program_code}</td>
              <td>
                TY{cell.tax_year}
                {/* The one thing Outcome said that was not about a filing, and
                    it is why `identified` is $0 on this row. */}
                {cell.is_base_year ? <span className="tcc-baseyear">base year</span> : null}
              </td>
              <td className="num">{cell.identified_usd == null ? '—' : money(Number(cell.identified_usd))}</td>
              <td className={`num tcc-margin-${reading.tone}`}>{reading.text}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export default function BookGrid({
  rows, filters, onFilter, onPickClient, onAskCopilot, unassessedCount,
  sort, onSort,
}) {
  const [open, setOpen] = useState(() => new Set());

  const toggle = useCallback((clientId) => {
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(clientId)) next.delete(clientId);
      else next.add(clientId);
      return next;
    });
  }, []);

  const all = rows || [];
  // Five clients. Filtering in the browser is the same call the coverage matrix
  // makes, and through the same grammar so a URL means one thing in both.
  const shown = useMemo(() => applyFilters(all, SPECS, filters), [all, filters]);

  const options = useMemo(() => ({
    band: presentValues(all, COLUMNS.band.read),
    industry: presentValues(all, COLUMNS.industry.read),
    program: presentValues(all, COLUMNS.program.read),
    state: presentValues(all, COLUMNS.state.read),
  }), [all]);

  // `SortHeader` takes an array because the trend grid supports a second key.
  // The book does not — the endpoint orders it, and one key is what the
  // endpoint can express — so it passes a single entry and hides shift-click.
  const sortKeys = useMemo(
    () => (sort ? [{ key: sort.key, desc: sort.desc }] : []),
    [sort],
  );
  const byValue = ranksByValue(sort);

  // Every state anyone in the book operates in, and every one we can price.
  // Union rather than per-client, because the map is the filter for the whole
  // book — and a state nobody operates in is not on it at all.
  //
  // Clients per state, deliberately NOT dollars. A claim is client-grain and a
  // client operates in several states, so any per-state money figure would
  // either double-count or attribute a credit to a state that did not earn it.
  const footprint = useMemo(() => {
    const clients = new Map();
    const priced = new Set();
    for (const row of all) {
      for (const s of row.states || []) {
        if (!clients.has(s)) clients.set(s, 0);
        clients.set(s, clients.get(s) + 1);
      }
      for (const s of row.priceable_states || []) priced.add(s);
    }
    const held = [...clients.keys()].sort();
    return {
      held,
      priced: [...priced].sort(),
      rows: held.map((code) => ({
        code,
        clients: clients.get(code),
        priceable: priced.has(code),
      })),
    };
  }, [all]);

  const selectedStates = useMemo(
    () => String(filters.state || '').split('|').map((s) => s.trim()).filter(Boolean),
    [filters.state],
  );

  // Clicking a state TOGGLES it in the shared filter grammar. The map does not
  // hold its own selection — if it did, a chip cleared from the filter bar
  // would leave the map still looking selected.
  const toggleState = useCallback((code) => {
    const next = selectedStates.includes(code)
      ? selectedStates.filter((s) => s !== code)
      : [...selectedStates, code];
    onFilter({ ...filters, state: next.join('|') });
  }, [filters, onFilter, selectedStates]);

  return (
    <section className="panel">
      {footprint.held.length > 1 ? (
        <details className="tcc-footprint" open>
          <summary>
            Where the book operates
            {selectedStates.length ? <b> · filtered to {selectedStates.join(', ')}</b> : null}
          </summary>
          {/* The map is two thirds whitespace on its own — we hold four states
              and the other forty-six are the picture. The list fills it with
              the thing the map is a control for, and gives the same filter a
              keyboard can reach. */}
          <div className="tcc-footprint-row">
            <FootprintMap
              states={footprint.held}
              priced={footprint.priced}
              selected={selectedStates}
              onSelect={toggleState}
            />
            <div className="tcc-footprint-list">
              <table className="tbl-compact">
                <thead>
                  <tr>
                    <th>State</th>
                    <th className="num">Clients</th>
                    <th>Statute</th>
                  </tr>
                </thead>
                <tbody>
                  {footprint.rows.map((s) => {
                    const on = selectedStates.includes(s.code);
                    return (
                      <tr key={s.code} className={on ? 'row-open' : undefined}>
                        <td>
                          <button
                            type="button"
                            className="tcc-cell-btn tcc-state-btn"
                            aria-pressed={on}
                            onClick={() => toggleState(s.code)}
                          >
                            {s.code}
                          </button>
                        </td>
                        <td className="num">{s.clients}</td>
                        <td className={s.priceable ? undefined : 'muted'}>
                          {s.priceable ? 'Priced' : 'No authored statute'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <p className="small muted">
                Clients, not dollars. A claim is client-grain and a client
                operates in several states, so a per-state total would either
                double-count or credit a state that did not earn it.
              </p>
              <p className="small muted">
                Selecting a state writes the same <code>state:</code> filter the
                bar below shows, so the map, this list and the chips cannot
                disagree.
              </p>
            </div>
          </div>
        </details>
      ) : null}

      <FilterBar
        specs={SPECS}
        filters={filters}
        shown={shown.length}
        total={all.length}
        noun="clients"
        onClear={() => onFilter({})}
      />

      {byValue ? (
        <p className="callout warn small">
          Ranked by value, not by targeting. That buries a client one
          hire from a threshold — they are worth $0 today, the same $0 as one
          fifty hires short.{' '}
          <button type="button" className="linklike" onClick={() => onSort?.('band')}>
            Return to targeting order
          </button>
        </p>
      ) : null}

      <div className="cov-scroll">
        <table className="cov-grid tbl-compact">
          <thead>
            <tr>
              <th className="cov-corner" />
              <th>
                Client
                <ColumnFilter
                  spec={COLUMNS.client}
                  value={filters.client || ''}
                  onChange={(v) => onFilter({ ...filters, client: v })}
                />
              </th>
              <th>
                Industry
                <ColumnFilter
                  spec={COLUMNS.industry}
                  value={filters.industry || ''}
                  options={options.industry}
                  onChange={(v) => onFilter({ ...filters, industry: v })}
                />
              </th>
              <SortHeader
                label="Targeting"
                sortKey="band"
                sort={sortKeys}
                onSort={onSort}
                multi={false}
                spec={COLUMNS.band}
                filters={filters}
                options={options.band}
                onFilter={(key, expr) => onFilter({ ...filters, [key]: expr })}
              />
              <th>
                Program
                <ColumnFilter
                  spec={COLUMNS.program}
                  value={filters.program || ''}
                  options={options.program}
                  onChange={(v) => onFilter({ ...filters, program: v })}
                />
              </th>
              <SortHeader label="Year" sortKey="year" sort={sortKeys} onSort={onSort} multi={false} />
              {/* The ONLY money column. Recoverable and exposure are both
                  `identified − claimed`, and no client here has a verified
                  filing — so both were arithmetic on an assertion. */}
              <SortHeader
                label="Identified"
                sortKey="identified"
                sort={sortKeys}
                onSort={onSort}
                multi={false}
                className="num"
              />
              <th>Ask</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((row) => {
              const expanded = open.has(row.client_id);
              const name = row.client_name || `Account ${row.client_id}`;
              const trend = trendReading(row.trend);
              return [
                <tr key={row.client_id} className={expanded ? 'row-open' : undefined}>
                  <td className="tcc-expander">
                    <button
                      type="button"
                      className="tcc-cell-btn"
                      aria-expanded={expanded}
                      aria-label={expanded ? `Collapse ${name}` : `Expand ${name}`}
                      onClick={() => toggle(row.client_id)}
                    >
                      {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </button>
                  </td>
                  <th scope="row" className="cov-rowhead">
                    <button
                      type="button"
                      className="cov-client"
                      aria-label={`Open ${name}`}
                      onClick={() => onPickClient?.(row.client_id)}
                    >
                      <span>{name}</span>
                      <ArrowRight size={12} />
                    </button>
                    {/* The band names the KIND of call; this names the size of
                        it, plus what the decline puts at risk. */}
                    {trend ? (
                      <span className="tcc-trend" title={`${trend.text} ${trend.detail}`}>
                        {trend.short}
                        {row.trend?.credit_earned_usd
                          ? ` · ${money(Number(row.trend.credit_earned_usd))} earned`
                          : ''}
                      </span>
                    ) : null}
                  </th>
                  <td className="small">{row.industry || <span className="muted">Not recorded</span>}</td>
                  <BandCell row={row} />
                  <td>{row.program_code || '—'}</td>
                  <td>{row.tax_year ? `TY${row.tax_year}` : '—'}</td>
                  <td className="num">{row.identified_usd == null ? '—' : money(Number(row.identified_usd))}</td>
                  <td>
                    <button
                      type="button"
                      className="btn btn-secondary tcc-ask"
                      aria-label={`Ask Copilot about ${name}`}
                      onClick={() => onAskCopilot?.(row)}
                    >
                      <MessageSquare size={13} /> Ask
                    </button>
                  </td>
                </tr>,
                expanded ? (
                  <tr key={`${row.client_id}-cells`} className="tcc-expand-row">
                    <td colSpan={8}>
                      <ExpandedCells clientId={row.client_id} />
                    </td>
                  </tr>
                ) : null,
              ];
            })}
          </tbody>
        </table>
      </div>

      {unassessedCount ? (
        <p className="small muted u-mt-2">
          {unassessedCount} of these have not been assessed for this year, so they
          carry no figure — not a zero. They sort below the assessed rather than
          among them, because ranking them together implies we looked.
        </p>
      ) : null}

      <p className="small muted">
        {byValue ? (
          <>
            Ranked by value. The default ranking is targeting — click
            that column to return to it.
          </>
        ) : (
          <>
            Ranked by targeting — the reason to act — not by dollar
            value. A client one hire from a threshold is worth $0 today — the
            same $0 as one fifty hires short — so ranking by value buries the
            customer most worth a call. Sort or filter any column to reorder.
          </>
        )}
      </p>
    </section>
  );
}
