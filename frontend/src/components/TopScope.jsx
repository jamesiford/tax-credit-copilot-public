import { CalendarRange } from 'lucide-react';

/**
 * The tax year, and only on the pages where it filters something.
 *
 * NOT on the book. A year there is a statement about statute, not about any
 * client: `calculableYears` has no payroll to narrow by at portfolio scope, so
 * it offered every authored GA year and opened on the newest — pinning Candle
 * Bottle, which holds one year of payroll, to TY2025. The book's question is
 * which client to call, which is about a client across every year they hold;
 * the year is chosen after one is picked, on the client page's own grid.
 *
 * Method is gone from here deliberately. Min-Max against Pay Period is the
 * difference between 539 and 656 eligible employees on the reference client,
 * and the statute has not chosen between them — the eligibility view says
 * outright that the methods are not expected to agree. As a dropdown in the
 * chrome it reads as a display preference, and somebody can read Min-Max for an
 * hour without noticing there is a second answer. It belongs on the page, next
 * to the figures it changes. It stays in the URL either way, so a shared link
 * still reproduces the reading.
 */
export const YEAR_FILTERS = new Set(['unit', 'employee']);

export default function TopScope({ options, scope, resolved, clientScope, page, error, onChange }) {
  // Absent, not disabled: the client grid IS the year dimension, so a selector
  // there is a control that appears to do something and does not. A greyed one
  // still asks to be clicked.
  //
  // A failed scope read is the exception. The bar is where the axes live, so it
  // is where their absence has to be explained -- silence here reads as "there
  // is nothing to choose" rather than "the list never loaded".
  if (!YEAR_FILTERS.has(page) && !error) return null;

  const years = options?.years?.authored || [];
  const heldButNotPriceable = new Set(clientScope?.payroll_without_statute || []);
  const notices = resolved?.notices || [];

  return (
    <div className="tcc-top-scope" role="region" aria-label="Scope">
      {error ? (
        <span className="tcc-top-error" title={error}>
          Scope unavailable. {error}
        </span>
      ) : null}
      {YEAR_FILTERS.has(page) ? (
        <label className="tcc-top-axis">
          <span className="sr-only">Tax year</span>
          <CalendarRange size={14} aria-hidden="true" />
          <select
            value={scope?.year ?? ''}
            onChange={(event) => onChange({ year: Number(event.target.value) })}
            title={notices.length ? notices.map((n) => n.message || n).join(' · ') : 'Tax year'}
          >
            {years.map((year) => (
              <option key={year} value={year}>
                TY{year}{heldButNotPriceable.has(year) ? ' · held, not priceable' : ''}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      {notices.length > 0 && (
        <span className="tcc-top-notice" title={notices.map((n) => n.message || n).join(' · ')}>
          {notices.length}
        </span>
      )}
    </div>
  );
}
