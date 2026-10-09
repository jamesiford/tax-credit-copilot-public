import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle, CheckCircle2, Loader2, TrendingUp,
} from 'lucide-react';
import { fetchInYearProgress } from '../api.js';
import { PORTFOLIO, derivedJurisdictions } from '../lib/scopeDimension.js';
import ProximityView from './ProximityView.jsx';

/**
 * How am I doing — in-year progress against the statutory finish line.
 *
 * The partner's named first operational test: run the calculation part-way
 * through the year, on the months that have closed, and answer two questions in
 * order — *are we on track*, and *who would move the needle*.
 *
 * The screen is deliberately one answer and one list. A client asking "how am I
 * doing" wants a yes or a no first; everything else is support for it.
 *
 * The list used to be eight rows rendered here and a hundred rendered on a
 * separate Near the line page. They were never two cohorts: the backend query
 * calls `handle_get_proximity` outright, precisely so the two screens could not
 * disagree. Two nav entries for one answer is how somebody comes away thinking
 * there are two. The full cohort is embedded below instead, method toggle and
 * band selector intact.
 *
 * **This is an estimate and says so in three places** — the badge, the
 * denominator line, and the method note. A run-rate projection rendered with the
 * same confidence as a calculated figure is how somebody files against a number
 * that was never a calculation.
 */

const num = (v) => (Number.isFinite(Number(v)) ? Number(v) : 0);
const usd = (v) => `$${num(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
const jobs = (v) => num(v).toFixed(2);

export default function ProgressView({ scope, scopeOptions, stack = null, yearOpen = false }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const state = useMemo(() => {
    const found = derivedJurisdictions(scope, scopeOptions);
    return found.length === 1 ? found[0].code : null;
  }, [scope, scopeOptions]);

  const year = scope.year;
  const isPortfolio = scope.clientId === PORTFOLIO;

  useEffect(() => {
    if (!state || !year || isPortfolio) { setData(null); return undefined; }
    let cancelled = false;
    setLoading(true);
    setError(null);
    const requested = { state, year, clientId: scope.clientId };
    fetchInYearProgress({ taxYear: year, state, accountId: scope.clientId })
      .then((payload) => { if (!cancelled) setData({ key: requested, data: payload }); })
      .catch((e) => { if (!cancelled) { setError(e.message); setData(null); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [state, year, scope.clientId, isPortfolio]);

  const fresh = data
    && data.key.state === state
    && data.key.year === year
    && data.key.clientId === scope.clientId;
  const payload = fresh ? data.data : null;

  const onTrack = payload?.on_track;

  if (!state || !year) {
    return (
      <div className="callout info">
        Select a single program so progress is measured against one statute.
      </div>
    );
  }

  return (
    <div className="prog-view">
      {/* The client page already names the client and the year in its
          breadcrumb and tab; this section names the QUESTION, in the same
          weight as "Near the line" below it, so the page reads as two halves. */}
      <header className="prox-header">
        <div>
          <h2>Are we on track · TY{year}</h2>
          {payload && !isPortfolio ? (
            <p className="prox-sub">
              <TrendingUp size={12} /> {payload.denominator_note}
            </p>
          ) : null}
        </div>
      </header>

      {/* The verdict is a question about one client's year. The cohort below is
          not, and works across the book, so portfolio scope loses the verdict
          rather than the whole page. */}
      {isPortfolio ? (
        <div className="callout info">
          Select one client for an on-track verdict. &ldquo;How am I doing&rdquo;
          is a question about a single client&rsquo;s year, and so is who is near
          the line — both are read from that client&rsquo;s run. The portfolio
          equivalent is What-if, which ranks clients by jobs to threshold.
        </div>
      ) : (
        <>
          {loading ? (
            <div className="prox-loading"><Loader2 size={16} className="spin" /> Calculating…</div>
          ) : null}
          {error ? <div className="prox-error">{error}</div> : null}
        </>
      )}

      {payload && !isPortfolio ? (
        <div className="prog-strip">
          {/* The answer, before any of the working — unless there is no base,
              in which case there is no answer and saying so is the answer. */}
          {payload.base_is_meaningful === false ? (
            <div className="prog-verdict unknown">
              <AlertTriangle size={20} />
              <div>
                <div className="prog-verdict-line">
                  Cannot judge progress — no base year to measure against.
                </div>
                <div className="prog-verdict-sub">{payload.base_caveat}</div>
              </div>
            </div>
          ) : (
            <div className={`prog-verdict ${onTrack ? 'on' : 'off'}`}>
              {onTrack ? <CheckCircle2 size={20} /> : <AlertTriangle size={20} />}
              <div>
                <div className="prog-verdict-line">
                  {onTrack ? 'On track to qualify' : `Short by ${jobs(payload.gap_to_finish)} jobs`}
                </div>
                <div className="prog-verdict-sub">
                  {jobs(payload.projected_net_new)} net new against a {jobs(payload.threshold)}-job
                  {' '}threshold · projected credit {usd(payload.projected_annual_credit_usd)} ·
                  {' '}as of {payload.as_of} · estimate
                </div>
              </div>
            </div>
          )}

          <div className="prog-figure">
            <span className="prog-figure-label">Headcount now</span>
            <span className="prog-figure-value">{jobs(payload.ytd_average_headcount)}</span>
            <span className="prog-figure-sub">
              avg of {payload.months_elapsed} closed months
            </span>
          </div>
          <div className="prog-figure">
            <span className="prog-figure-label">Base year</span>
            <span className="prog-figure-value">
              {payload.has_prior_year_payroll ? jobs(payload.prior_year_average_headcount) : '—'}
            </span>
            <span className="prog-figure-sub">
              {payload.has_prior_year_payroll ? `TY${year - 1}, frozen` : `no TY${year - 1} payroll held`}
            </span>
          </div>
          <div className="prog-figure accent">
            <span className="prog-figure-label">Finish line</span>
            <span className="prog-figure-value">{jobs(payload.finish_line_headcount)}</span>
            <span className="prog-figure-sub">base + {jobs(payload.threshold)} jobs</span>
          </div>
        </div>
      ) : null}

      <ProximityView scope={scope} scopeOptions={scopeOptions} embedded stack={stack} yearOpen={yearOpen} />
    </div>
  );
}
