import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ChevronDown, ChevronUp } from 'lucide-react';
import InsightBar from '../components/InsightBar.jsx';
import BookGrid, { filterBookRows } from '../components/BookGrid.jsx';
import FootprintPanel from '../components/FootprintPanel.jsx';
import GridTabs, { GridTabPanel } from '../components/GridTabs.jsx';
import StartHereCards from '../components/StartHereCards.jsx';
import RunDialog from '../components/runs/RunDialog.jsx';
import SelectionBar from '../components/runs/SelectionBar.jsx';
import Card from '../components/ui/Card.jsx';
import DegradedBanner from '../components/ui/DegradedBanner.jsx';
import EmptyState from '../components/ui/EmptyState.jsx';
import HeroBand from '../components/ui/HeroBand.jsx';
import KpiTile, { KpiRow } from '../components/ui/KpiTile.jsx';
import SectionHeading from '../components/ui/SectionHeading.jsx';
import { fetchPortfolioV2 } from '../api.js';
import { portfolioAnswer } from '../lib/answers.js';
import {
  activeBookTab, bandCounts, bookTabs, filtersForTab, footprintOf, selectedStates, tileTone,
} from '../lib/bookCards.js';
import { band } from '../lib/priority.js';
import { formatFilters, parseFilters } from '../lib/gridFilter.js';
import { bookSortQuery, formatBookSort, parseBookSort, toggleBookSort } from '../lib/bookSort.js';
import { greeting } from '../lib/identity.js';
import { emptySelection, serverFilter, setPage, toggleId } from '../lib/runBatches.js';
import { loadStartHere, storeStartHere } from '../lib/startHere.js';

/**
 * The book. Every client, ranked by why you would call them.
 *
 * This page used to be two tabs — the coverage matrix, and a "Who to call" list
 * from `/api/claims/proximity`. They were never two datasets: the second read
 * the same claims and kept only cells within one job of a threshold. The split
 * meant a reader had to know which tab held the answer before they knew what
 * the answer was — and a client sitting on a large unclaimed credit was
 * invisible in one while a client one hire short was invisible in the other.
 *
 * One grid now, ordered by `PriorityBand`. The band is a NAMED reason, not a
 * score: blending dollars and jobs needs coefficients nobody can justify, and
 * this ranking exists to be read aloud on a call.
 *
 * The matrix is not lost. It is what expanding a row shows, which is also where
 * "which programmes, which years" is actually answered.
 */

//: The grid knows these columns; anything else in the URL is dropped at parse.
const FILTER_KEYS = {
  client: 1, band: 1, program: 1, year: 1, identified: 1, margin: 1, state: 1,
};

export default function PortfolioPage({
  onPickClient, onAskCopilot, scopeOptions, identity = null,
}) {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);
  const [search, setSearch] = useSearchParams();
  const navigate = useNavigate();
  const headingRef = useRef(null);

  // "Start here" is a view preference: open for somebody who has never seen the
  // page, and closed once they have put it away.
  const [startOpen, setStartOpen] = useState(() => loadStartHere());
  const toggleStart = useCallback(() => {
    setStartOpen((open) => { storeStartHere(!open); return !open; });
  }, []);

  const showBook = useCallback(() => {
    const node = headingRef.current;
    if (!node) return;
    node.focus({ preventScroll: true });
    if (typeof node.scrollIntoView === 'function') node.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }, []);

  // NO YEAR. The book asks which client to call, and that is a question about a
  // client across every year they hold — an unclaimed year from four years ago
  // is still recoverable retroactively, and a year filter buries it. Worse, the
  // year on offer was a STATUTE year rather than a payroll year, so a client
  // holding one year of payroll was pinned to a year it has none of. The year
  // is chosen after a client is, on that client's own grid.

  const filters = useMemo(
    () => parseFilters(FILTER_KEYS, search.get('bf')),
    [search],
  );

  const setFilters = useCallback((next) => {
    const params = new URLSearchParams(search);
    const wire = formatFilters(next);
    if (wire) params.set('bf', wire);
    else params.delete('bf');
    setSearch(params, { replace: true });
  }, [search, setSearch]);

  // `bsort`, not `sort`. The trend grid owns `sort` and parses it against its
  // own columns; one name for two grammars is how a shared URL renders one
  // page correctly and the other silently unsorted.
  const sort = useMemo(() => parseBookSort(search.get('bsort')), [search]);

  const setSort = useCallback((key) => {
    const params = new URLSearchParams(search);
    const wire = formatBookSort(toggleBookSort(sort, key));
    if (wire) params.set('bsort', wire);
    else params.delete('bsort');
    setSearch(params, { replace: true });
  }, [search, setSearch, sort]);

  useEffect(() => {
    let cancelled = false;
    // The ORDER is the endpoint's job, so the page asks for one rather than
    // re-sorting what came back: sorting a page of 200 in the browser would
    // disagree with the total the moment the book outgrows one page.
    const { sort: field, order } = bookSortQuery(sort);
    fetchPortfolioV2({ sort: field, order, limit: 200 })
      .then((body) => { if (!cancelled) { setSummary(body); setError(null); } })
      .catch((e) => { if (!cancelled) { setSummary(null); setError(e.message); } });
    return () => { cancelled = true; };
  }, [sort.key, sort.desc]);

  const rows = summary?.items || [];
  const counts = useMemo(() => bandCounts(rows), [rows]);

  // Selecting clients to run. The filters narrow the screen in the browser, so "all matching" is exact when the page
  // holds the whole book (explicit ids), and is handed to the server as a filter only when it can be written in the
  // server's vocabulary; otherwise the bar says why it cannot, rather than running clients nobody saw.
  const [selection, setSelection] = useState(emptySelection);
  const [runOpen, setRunOpen] = useState(false);
  const shown = useMemo(() => filterBookRows(rows, filters), [rows, filters]);
  const matching = useMemo(() => {
    if (!rows.length) return null;
    const total = summary?.total ?? rows.length;
    if (rows.length >= total) return { ok: true, count: shown.length, explicit: shown.map((r) => r.client_id) };
    const translated = serverFilter(filters);
    if (!translated.ok) return { ok: false, count: null, reason: translated.reason };
    const unfiltered = Object.keys(translated.filter).length === 0;
    return { ok: true, count: unfiltered ? total : null, filter: translated.filter };
  }, [rows, summary, shown, filters]);
  const selectMatching = useCallback(() => {
    if (!matching?.ok) return;
    setSelection(matching.explicit
      ? { ids: matching.explicit, matching: null }
      : { ids: [], matching: { count: matching.count, filter: matching.filter } });
  }, [matching]);
  const started = useCallback((batch) => {
    setRunOpen(false);
    setSelection(emptySelection());
    navigate(`/runs/${encodeURIComponent(batch.batch_id)}`);
  }, [navigate]);
  const activeTab = activeBookTab(filters);

  // 29 Sep: the caption is the COUNTS only. It used to name the single client
  // closest to qualifying and a "top target", which the grid beneath already
  // ranks — the Copilot summary is where a reader asks for the story.
  const answer = portfolioAnswer(summary, null);

  const askAbout = useCallback((row) => {
    const name = row.client_name || `Account ${row.client_id}`;
    onAskCopilot?.(
      `Brief me on ${name}: what is their situation and why would I call them?`,
      // Answers about THIS client, whoever the shell has selected. The year is
      // the row's own — the book no longer has one to lend it.
      { clientId: row.client_id, taxYear: row.tax_year ?? null },
    );
  }, [onAskCopilot]);

  const header = (
    <HeroBand
      compact
      title={greeting(identity)}
      aside={(
        <button
          type="button"
          className="start-here-toggle"
          aria-expanded={startOpen}
          aria-controls="start-here"
          onClick={toggleStart}
        >
          {startOpen ? <ChevronUp size={16} aria-hidden="true" /> : <ChevronDown size={16} aria-hidden="true" />}
          Start here
        </button>
      )}
    >
      Who to target — new clients and existing ones — ranked by the reason to act, not by dollar value.
    </HeroBand>
  );

  const cards = startOpen ? (
    <StartHereCards
      id="start-here"
      firstClientId={rows[0]?.client_id ?? null}
      onNavigate={(href) => navigate(href)}
      onShowBook={showBook}
    />
  ) : null;

  if (error) {
    return (
      <div>
        {header}
        <EmptyState title="The book is unavailable">
          {error}<br />Nothing was changed; reload the page to try again.
        </EmptyState>
      </div>
    );
  }

  return (
    <div>
      {header}
      {cards}
      <DegradedBanner degraded={summary?.degraded} />
      <SectionHeading className="book-heading">
        <span id="targeting" ref={headingRef} tabIndex={-1}>Targeting</span>
      </SectionHeading>
      {answer ? (
        <InsightBar
          caption={answer.replace(/\.$/, '')}
          notes={[
            summary?.unassessed_clients
              ? `${summary.unassessed_clients} client(s) have not been assessed yet, so they carry no figure — not a zero.`
              : null,
            summary?.unavailable_clients
              ? `${summary.unavailable_clients} client(s) are unavailable: whether they were assessed is unknown. That is not "not assessed".`
              : null,
          ]}
          request={{ page: 'portfolio' }}
        />
      ) : null}

      <Card
        className="tcc-book-card"
        flush
        title="The book"
        tabs={rows.length ? (
          <GridTabs
            label="Population"
            tabs={bookTabs(rows)}
            active={activeTab ?? ''}
            onChange={(id) => setFilters(filtersForTab(filters, id))}
          />
        ) : null}
        footer={rows[0] ? (
          <div className="tcc-book-foot">
            <span>First on the list</span>
            <button type="button" className="tcc-link" onClick={() => onPickClient?.(rows[0].client_id)}>
              Open {rows[0].client_name || `Account ${rows[0].client_id}`} →
            </button>
          </div>
        ) : null}
      >
        <GridTabPanel id={activeTab ?? 'all'} active={activeTab ?? 'all'}>
          <BookGrid
            rows={rows}
            filters={filters}
            onFilter={setFilters}
            sort={sort}
            onSort={setSort}
            onPickClient={onPickClient}
            onAskCopilot={askAbout}
            selection={selection}
            onToggleRow={(id) => setSelection((cur) => toggleId(cur, id))}
            onTogglePage={(ids, on) => setSelection((cur) => setPage(cur, ids, on))}
            unassessedCount={summary?.unassessed_clients || 0}
            unavailableHint={(summary?.degraded || []).find((d) => d.dependency === 'claims_store')?.remedy}
          />
        </GridTabPanel>
      </Card>

      <SelectionBar
        selection={selection}
        matching={matching}
        onSelectMatching={selectMatching}
        onClear={() => setSelection(emptySelection())}
        onRun={() => setRunOpen(true)}
      />
      <RunDialog
        open={runOpen}
        selection={selection}
        scopeOptions={scopeOptions}
        onClose={() => setRunOpen(false)}
        onStarted={started}
      />

      <div className="tcc-card-grid">
        {footprintOf(rows).held.length > 1 ? (
          <Card
            title="Where the book operates"
            subtitle={selectedStates(filters).length
              ? `Filtered to ${selectedStates(filters).join(', ')}`
              : 'Choose a state to filter the book'}
          >
            <FootprintPanel rows={rows} filters={filters} onFilter={setFilters} />
          </Card>
        ) : null}
        {counts.length ? (
          <Card title="Position" subtitle="Clients by the reason to act, not by dollar value">
            <KpiRow label="Clients by targeting band">
              {counts.map(({ id, count }) => (
                <KpiTile
                  key={id}
                  label={band(id).label}
                  value={String(count)}
                  sub={band(id).line}
                  tone={tileTone(id)}
                />
              ))}
            </KpiRow>
          </Card>
        ) : null}
      </div>
    </div>
  );
}
