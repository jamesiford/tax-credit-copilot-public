import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  AlertTriangle, Building2, Loader2, RefreshCw, ShieldAlert, TrendingUp,
} from 'lucide-react';
import {
  assessClient, fetchClientCoverage, fetchPortfolioCoverage,
} from '../api.js';
import FootprintMap from './FootprintMap.jsx';
import PageHeader from './PageHeader.jsx';
import StatCard, { StatRow } from './StatCard.jsx';
import { PORTFOLIO } from '../lib/scopeDimension.js';
import { TEXT, applyFilters } from '../lib/gridFilter.js';
import { ColumnFilter, FilterBar } from './ColumnFilter.jsx';
import {
  BASE_YEAR_NOTE, USD, buildGrid, cellReading, isBaseYear, money, outcomeMeta,
  summarise, withUnassessedClients,
} from '../lib/coverage.js';

/**
 * Position — replaces Overview.
 *
 * Portfolio scope renders the client x program coverage matrix; account scope
 * renders the program x year variance grid, which IS the audit deliverable a
 * consultant puts in front of a client.
 *
 * The rule this view exists to honour: a cell is a variance, not a status.
 * Under-claimed is recoverable revenue and over-claimed is exposure, and both
 * are shown. Suppressing the second while advertising the first would be
 * indefensible the first time an authority found one.
 */

function Totals({ summary, label }) {
  // Recoverable and exposure are both `identified − claimed`. When the claimed
  // side was asserted rather than filed, the difference inherits that and has
  // to say so — otherwise the two most prominent figures on the screen read as
  // computed while resting on something nobody verified.
  const restsOnAssertion = summary.unverified > 0;
  return (
    <StatRow>
      {/* Tone carries the READING. Recoverable is money we can go and get, so
          it is good; exposure is a finding against us, so it is bad. Cells
          assessed is a denominator and has no reading at all — it used to be
          blue, the same blue as exposure, which made the colour meaningless. */}
      <StatCard
        label="Recoverable"
        value={USD.format(summary.opportunity)}
        sub={restsOnAssertion ? `${label} · vs an unverified claim` : label}
        tone="good"
      />
      <StatCard
        label="Exposure"
        value={USD.format(summary.exposure)}
        sub={summary.hasExposure
          ? `${summary.exposureCells} cell${summary.exposureCells === 1 ? '' : 's'} over-claimed`
          : null}
        tone="bad"
        empty={!summary.hasExposure}
      />
      <StatCard label="Cells assessed" value={summary.cells} />
      <StatCard
        label="Unverified"
        value={summary.unverified}
        sub={summary.unverified ? 'client-asserted, not computed' : null}
        tone="warn"
        empty={!summary.unverified}
      />
    </StatRow>
  );
}

function Cell({ cell, onOpen }) {
  const reading = cellReading(cell);
  if (!cell) {
    return <td className="cov-cell cov-empty" title="No record for this program-year"><span>·</span></td>;
  }
  const title = reading.baseYear
    ? `${reading.label} · ${BASE_YEAR_NOTE}`
    : `${reading.label} · identified ${USD.format(reading.identified)} · claimed ${USD.format(reading.claimed)}`;
  return (
    <td className={`cov-cell cov-${reading.tone}`}>
      <button type="button" onClick={() => onOpen?.(cell)} title={title}>
        <span className="cov-amount">{reading.baseYear ? '—' : money(reading.amount)}</span>
        <span className="cov-label">{reading.label}</span>
        {!reading.verified && !reading.baseYear
          && <span className="cov-unverified" title="Asserted, not computed or confirmed">unverified</span>}
      </button>
    </td>
  );
}

function AccountGrid({ coverage, scopeWindow, onOpen }) {
  const grid = useMemo(
    () => buildGrid(coverage?.cells, { years: scopeWindow }),
    [coverage, scopeWindow],
  );
  // Summed as Decimal by the API. The grid used to reduce them here, which is
  // adding money as a float on the one screen that reports a variance.
  const programTotals = coverage?.program_totals;
  const hasBaseYear = useMemo(
    () => (coverage?.cells || []).some(isBaseYear),
    [coverage],
  );

  if (!grid.programs.length) {
    return (
      <div className="callout info">
        Nothing assessed for this client yet. Run an assessment to compute what
        each program-year is worth.
      </div>
    );
  }

  return (
    <div className="cov-scroll">
      <table className="cov-grid">
        <thead>
          <tr>
            <th className="cov-corner">Program</th>
            {grid.years.map((y) => <th key={y}>TY{y}</th>)}
            <th className="cov-total">Recoverable</th>
            <th className="cov-total">Exposure</th>
          </tr>
        </thead>
        <tbody>
          {grid.programs.map((program) => {
            const cells = grid.years.map((y) => grid.at(program, y));
            // Read, never re-derived: the API sums the row as Decimal.
            const totals = summarise(programTotals?.[program]);
            return (
              <tr key={program}>
                <th scope="row" className="cov-rowhead">{program}</th>
                {cells.map((cell, i) => (
                  <Cell key={grid.years[i]} cell={cell} onOpen={onOpen} />
                ))}
                <td className="cov-total">{totals.opportunity ? USD.format(totals.opportunity) : '—'}</td>
                <td className={`cov-total ${totals.exposure ? 'cov-exposure' : ''}`}>
                  {totals.exposure ? USD.format(totals.exposure) : '—'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {hasBaseYear ? <p className="small muted">{BASE_YEAR_NOTE}</p> : null}
    </div>
  );
}

/**
 * The matrix filters CLIENT-SIDE on five rows, which is the same call the
 * client grid makes for 36 and the opposite of the unit grid's 10,236. Where
 * the work happens is a function of how many rows there are, not a house style.
 *
 * Outcome is deliberately NOT a filter here. A cell already carries its outcome
 * as a colour and a word, and hiding the exposures is the one thing this view
 * exists not to do.
 */
const CLIENT_COLUMN = {
  key: 'client', label: 'Client', type: TEXT, read: (row) => row.name,
};

function PortfolioMatrix({
  coverage, clientsById, book, onPick, onAssess, assessingId, filters, onFilter,
}) {
  const all = useMemo(
    () => withUnassessedClients(coverage.clients || [], book || [])
      .map((client) => ({
        ...client,
        name: clientsById.get(client.client_id)?.name
          || client.name || `Account ${client.client_id}`,
      })),
    [coverage.clients, book, clientsById],
  );
  const ranked = useMemo(
    () => applyFilters(all, { client: CLIENT_COLUMN }, filters),
    [all, filters],
  );
  const programs = useMemo(() => {
    const seen = new Set();
    (coverage.clients || []).forEach((c) => c.cells.forEach((cell) => seen.add(cell.program_code)));
    return [...seen].sort();
  }, [coverage.clients]);

  if (!all.length) {
    return (
      <div className="callout info">
        No clients in scope.
      </div>
    );
  }

  return (
    <>
      <FilterBar
        specs={{ client: CLIENT_COLUMN }}
        filters={filters}
        shown={ranked.length}
        total={all.length}
        noun="clients"
        onClear={() => onFilter('')}
      />
      {ranked.length ? null : (
        <div className="callout info">No client matches that filter.</div>
      )}
      <div className="cov-scroll">
        <table className="cov-grid">
          <thead>
            <tr>
              <th className="cov-corner">
                Client
                <ColumnFilter
                  spec={CLIENT_COLUMN}
                  value={filters.client || ''}
                  onChange={onFilter}
                />
              </th>
              {programs.map((p) => <th key={p}>{p}</th>)}
              <th className="cov-total">Recoverable</th>
              <th className="cov-total">Exposure</th>
            </tr>
          </thead>
          <tbody>
            {ranked.map((client) => {
              const { name } = client;
              const head = (
                <th scope="row" className="cov-rowhead">
                  <button type="button" className="cov-client" onClick={() => onPick?.(client.client_id)}>
                    <Building2 size={13} />
                    {name}
                  </button>
                </th>
              );

              // Nobody has looked at this client. That is not $0 recoverable, so
              // the row says so and offers the run rather than filling with dashes.
              if (client.unassessed) {
                const busy = assessingId === client.client_id;
                return (
                  <tr key={client.client_id} className="cov-row-unassessed">
                    {head}
                    {programs.length ? (
                      <td className="cov-cell cov-empty" colSpan={programs.length}>
                        <span>Not assessed</span>
                      </td>
                    ) : null}
                    <td className="cov-total" colSpan={2}>
                      <button type="button" className="tcc-link" disabled={busy} onClick={() => onAssess?.(client.client_id)}>
                        {busy ? 'Assessing…' : 'Run assessment'}
                      </button>
                    </td>
                  </tr>
                );
              }

              const totals = summarise(client.totals);
              const byProgram = new Map();
              client.cells.forEach((cell) => {
                // Years roll up at portfolio scope, so a client with an exposure
                // in any year must show as an exposure here — otherwise a good
                // year would mask a bad one.
                const prior = byProgram.get(cell.program_code);
                if (!prior || outcomeMeta(cell.outcome).rank < outcomeMeta(prior.outcome).rank) {
                  byProgram.set(cell.program_code, cell);
                }
              });
              return (
                <tr key={client.client_id}>
                  {head}
                  {programs.map((p) => <Cell key={p} cell={byProgram.get(p)} />)}
                  <td className="cov-total">{totals.opportunity ? USD.format(totals.opportunity) : '—'}</td>
                  <td className={`cov-total ${totals.hasExposure ? 'cov-exposure' : ''}`}>
                    {totals.hasExposure ? USD.format(totals.exposure) : '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}

export default function PositionView({
  scope, scopeWindow, scopeOptions, clientScope, onPickClient, embedded = false,
}) {
  // Coverage travels WITH the scope it describes. Two separate pieces of state
  // let a render happen where the scope has changed but the data has not — the
  // account grid reading a portfolio payload, or worse, one client's figures
  // under another's heading. Keeping them in one object makes that
  // unrepresentable rather than merely unlikely.
  const [loaded, setLoaded] = useState(null);   // { key, data }
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [assessing, setAssessing] = useState(false);
  const [assessingClient, setAssessingClient] = useState(null);
  const [declined, setDeclined] = useState([]);

  const isPortfolio = scope.clientId === PORTFOLIO;
  // In the URL, like every other filter, so a narrowed book is shareable.
  const [search, setSearch] = useSearchParams();
  const clientQ = search.get('client_q') || '';
  const clientFilter = useMemo(() => (clientQ ? { client: clientQ } : {}), [clientQ]);
  const setClientFilter = useCallback((expr) => {
    const next = new URLSearchParams(search);
    if (expr) next.set('client_q', expr);
    else next.delete('client_q');
    setSearch(next, { replace: true });
  }, [search, setSearch]);
  // The window is part of the key: totals must describe exactly the cells the
  // grid shows, or a headline covers years that are not on screen.
  const years = useMemo(() => (scopeWindow || []).filter((y) => y != null), [scopeWindow]);
  const scopeKey = `${scope.clientId}:${years.join(',')}`;
  const clientsById = useMemo(
    () => new Map((scopeOptions?.clients || []).map((c) => [c.account_id, c])),
    [scopeOptions],
  );

  // States we hold authored statute for. A payroll state we cannot price is a
  // real gap in coverage and the map says so rather than shading it the same.
  const pricedStates = useMemo(
    () => (scopeOptions?.programs || [])
      .filter((p) => p.calculable)
      .map((p) => p.jurisdiction?.code)
      .filter(Boolean),
    [scopeOptions],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = isPortfolio
        ? await fetchPortfolioCoverage()
        : await fetchClientCoverage(scope.clientId, { taxYears: years });
      setLoaded({ key: scopeKey, data });
    } catch (reason) {
      setError(String(reason));
      setLoaded(null);
    } finally {
      setLoading(false);
    }
  }, [isPortfolio, scope.clientId, scopeKey, years]);

  useEffect(() => { setDeclined([]); load(); }, [load]);

  // Only render coverage that belongs to the CURRENT scope.
  const coverage = loaded?.key === scopeKey ? loaded.data : null;

  const runAssessment = async () => {
    if (isPortfolio) return;
    setAssessing(true);
    setError(null);
    try {
      const result = await assessClient(scope.clientId);
      setDeclined(result.declined || []);
      await load();
    } catch (reason) {
      setError(String(reason));
    } finally {
      setAssessing(false);
    }
  };

  const assessOne = useCallback(async (clientId) => {
    setAssessingClient(clientId);
    setError(null);
    try {
      await assessClient(clientId);
      await load();
    } catch (reason) {
      setError(String(reason));
    } finally {
      setAssessingClient(null);
    }
  }, [load]);

  const summary = summarise(coverage?.totals);
  const heading = isPortfolio
    ? 'The book'
    : `Position — ${clientsById.get(scope.clientId)?.name || `Account ${scope.clientId}`}`;

  return (
    <>
      {embedded ? (
        <h2 className="panel-title">What was claimed</h2>
      ) : (
        <PageHeader
          eyebrow="What is it worth"
          title={heading}
          sub={isPortfolio
            ? 'Every client, assessed or not, against what they were entitled to.'
            : 'What was claimed each year, against what they were entitled to.'}
          actions={!isPortfolio ? (
            <button className="btn btn-primary" disabled={assessing} onClick={runAssessment}>
              {assessing ? <Loader2 size={15} className="spin" /> : <RefreshCw size={15} />}
              {assessing ? 'Assessing…' : 'Run assessment'}
            </button>
          ) : null}
        />
      )}
      {embedded ? (
        <p className="page-sub">What was claimed each year, against what they were entitled to.</p>
      ) : null}
      {embedded && !isPortfolio ? (
        <div className="tcc-header-actions tcc-embedded-actions">
          <button className="btn btn-secondary" disabled={assessing} onClick={runAssessment}>
            {assessing ? <Loader2 size={15} className="spin" /> : <RefreshCw size={15} />}
            {assessing ? 'Assessing…' : 'Run assessment'}
          </button>
        </div>
      ) : null}

      {error && <div className="callout warn">{error}</div>}

      {coverage && (
        <>
          <Totals summary={summary} label={isPortfolio ? 'across the book' : 'across the window'} />
          {/* Below the figures, not above them. Four attention-grabbing blocks
              before any data is not emphasis, it is noise. */}
          {summary.hasExposure && (
            <div className="callout warn">
              <ShieldAlert size={16} />
              <div>
                <b>{USD.format(summary.exposure)} claimed above what we compute as substantiated.</b>{' '}
                Surfaced deliberately: an audit that reports only recoverable dollars is
                not an audit.
              </div>
            </div>
          )}
          {isPortfolio
            ? (
              <PortfolioMatrix
                coverage={coverage}
                clientsById={clientsById}
                book={scopeOptions?.clients}
                onPick={onPickClient}
                onAssess={assessOne}
                assessingId={assessingClient}
                filters={clientFilter}
                onFilter={setClientFilter}
              />
            )
            : <AccountGrid coverage={coverage} scopeWindow={years} />}
        </>
      )}

      {loading && !coverage && (
        <div className="callout info"><Loader2 size={15} className="spin" /> Reading coverage…</div>
      )}

      {declined.length > 0 && (
        <section className="panel">
          <h3 className="panel-title">
            Declined <span className="right">no authored statute</span>
          </h3>
          <p className="small muted">
            These program-years were not calculated. Statute is not inherited across
            years, so a figure under a neighbouring year&apos;s rules would be a wrong
            answer rather than an approximation.
          </p>
          <ul className="cov-declined">
            {declined.map((d) => (
              <li key={`${d.program_code}-${d.tax_year}`}>
                <AlertTriangle size={13} />
                <b>{d.program_code}{d.tax_year ? ` TY${d.tax_year}` : ''}</b>
                <span>{d.detail}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {coverage && !isPortfolio && (coverage.engagements || []).length > 0 && (
        <section className="panel">
          <h3 className="panel-title">Engagement scope <span className="right">what we are mandated to handle</span></h3>
          <ul className="cov-engagements">
            {coverage.engagements.map((e) => (
              <li key={e.program_code}>
                <b>{e.program_code}</b>
                <span className={`cov-scope cov-scope-${e.scope}`}>{e.scope.replace(/_/g, ' ')}</span>
                {e.note && <em>{e.note}</em>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {!isPortfolio && (clientScope?.states || []).length > 0 && (
        <section className="panel">
          <h3 className="panel-title">
            Footprint
            <span className="right">
              {clientScope.states.length} state{clientScope.states.length === 1 ? '' : 's'}
              {clientScope.rows ? ` · ${clientScope.rows.toLocaleString()} payroll rows` : ''}
            </span>
          </h3>
          <div className="tcc-footprint-cap">
            <FootprintMap states={clientScope.states} priced={pricedStates} />
          </div>
        </section>
      )}
    </>
  );
}
