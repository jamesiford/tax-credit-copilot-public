import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import InsightBar from '../components/InsightBar.jsx';
import BookGrid from '../components/BookGrid.jsx';
import PageHeader from '../components/PageHeader.jsx';
import { fetchPortfolioV2 } from '../api.js';
import { portfolioAnswer } from '../lib/answers.js';
import { formatFilters, parseFilters } from '../lib/gridFilter.js';
import { bookSortQuery, formatBookSort, parseBookSort, toggleBookSort } from '../lib/bookSort.js';

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

export default function PortfolioPage({ onPickClient, onAskCopilot, scopeOptions }) {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);
  const [search, setSearch] = useSearchParams();

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
    <PageHeader
      eyebrow="Portfolio"
      title="Targeting"
      sub="Who to target — new clients and existing ones — ranked by the reason to act, not by dollar value."
    />
  );

  if (error) {
    return <div>{header}<div className="callout warn">The book could not be read: {error}</div></div>;
  }

  return (
    <div>
      {header}
      {answer ? (
        <InsightBar
          caption={answer.replace(/\.$/, '')}
          notes={[
            summary?.unassessed_clients
              ? `${summary.unassessed_clients} client(s) have not been assessed yet, so they carry no figure — not a zero.`
              : null,
          ]}
          request={{ page: 'portfolio' }}
        />
      ) : null}

      <BookGrid
        rows={rows}
        filters={filters}
        onFilter={setFilters}
        sort={sort}
        onSort={setSort}
        onPickClient={onPickClient}
        onAskCopilot={askAbout}
        unassessedCount={summary?.unassessed_clients || 0}
      />
    </div>
  );
}
