import { useEffect, useMemo, useState } from 'react';
import { BookOpenCheck, Loader2, ShieldCheck } from 'lucide-react';
import { fetchRules } from '../api.js';
import { authoredYearsLabel } from '../lib/reference.js';
import { PageHeader } from './ReferenceViews.jsx';
import SortHeader from './SortHeader.jsx';
import { FilterBar } from './ColumnFilter.jsx';
import useTableControls from './useTableControls.js';
import { ENUM, NUMERIC, TEXT } from '../lib/gridFilter.js';

/**
 * Rules — statute and methodology, in one place and clearly separated.
 *
 * Two tabs because they answer different questions and freeze on different
 * clocks. **Statute** is what a legislature published, versioned per tax year
 * [ADR-005] and authored with a citation. **Methodology** is how we measure,
 * frozen in an assumption set and reconciled with the partner.
 *
 * Collapsing them, as the old Rule Library did, makes a statutory amendment and
 * a change in our own method look like the same kind of event. They are not: one
 * is a fact about the world, the other is a decision we are accountable for.
 *
 * There is deliberately no rule-ingestion control here. The "Re-run ingestion"
 * and "Check against DCA source" panels changed nothing the calculation reads:
 * the refresh returned a captured snapshot without touching the network, and an
 * applied rulebook landed in process memory no calculation consulted. Statute
 * arrives as an authored year pack in git, which is what the table below lists.
 */

export default function RuleLibraryView({ onAskCopilot, programs = null }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetchRules()
      .then((payload) => { if (!cancelled) setData(payload); })
      .catch((reason) => { if (!cancelled) setError(String(reason)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const rules = useMemo(() => data?.rules || [], [data]);
  // Which tax years each programme can actually calculate comes from the scope
  // payload the shell already holds, not from the pack's own metadata: a pack
  // can carry a one-off threshold for a year without a year pack behind it.
  const authored = useMemo(() => new Map(
    (programs || []).map((p) => [p.program_code, p.authored_years || []]),
  ), [programs]);
  const yearsFor = (code) => authored.get(code) || [];
  const verified = rules.filter((r) => r.verified).length;
  const columns = useMemo(() => ({
    name: { key: 'name', label: 'Program', type: TEXT, read: (r) => r.name },
    jurisdiction: { key: 'jurisdiction', label: 'Where', type: ENUM, read: (r) => r.jurisdiction },
    citation: { key: 'citation', label: 'Citation', type: TEXT, read: (r) => r.citation },
    years: {
      key: 'years', label: 'Tax years', type: NUMERIC, filterable: false,
      read: (r) => (authored.get(r.code) || []).length,
    },
    filing: { key: 'filing', label: 'Filing window', type: TEXT, read: (r) => r.filing?.window },
    threshold: { key: 'threshold', label: 'Min jobs', type: NUMERIC, read: (r) => r.threshold },
    benefit: { key: 'benefit', label: 'Benefit yrs', type: NUMERIC, read: (r) => r.benefit_period_years },
    review: {
      key: 'review', label: 'Review', type: ENUM, read: (r) => (r.verified ? 'signed' : 'pending'),
    },
  }), [authored]);
  const table = useTableControls(columns, rules);
  const yearScoped = programs ? rules.filter((r) => yearsFor(r.code).length > 0).length : null;

  return <>
    <PageHeader
      eyebrow="Prove it"
      title="Programs"
      sub="What each jurisdiction published, versioned by tax year, with the citation each value came from"
      actions={onAskCopilot && (
        <button
          className="btn btn-primary"
          onClick={() => onAskCopilot('Summarize how rule packs are versioned per tax year, and how a filed claim stays bound to the statute that was in force that year.')}
        >
          Ask Copilot
        </button>
      )}
    />

    {error && <div className="callout warn">{error}</div>}
    {loading && <div className="callout info"><Loader2 size={15} className="spin" /> Reading rule packs…</div>}

    <div className="callout info">
      <b>Statute is frozen per tax year.</b> Georgia&apos;s minimum weekly wage was
      $541 in 2020 and $636 in 2023. A retroactive audit prices each year under
      the rules in force <i>that</i> year, and a year with no authored pack is
      declined by name rather than estimated from its neighbour.
    </div>

    <div className="kpi-strip tcc-kpi-4">
      <div className="kpi-card">
        <div className="kpi-label">Programs codified</div>
        <div className="kpi-value">{rules.length}</div>
      </div>
      <div className="kpi-card accent">
        <div className="kpi-label">Calculable</div>
        <div className="kpi-value">{yearScoped ?? '—'}</div>
        <div className="kpi-sub">statute authored by tax year</div>
      </div>
      <div className="kpi-card green">
        <div className="kpi-label">Signed off</div>
        <div className="kpi-value">{verified}</div>
        <div className="kpi-sub">by a practitioner</div>
      </div>
      <div className="kpi-card">
        <div className="kpi-label">Awaiting review</div>
        <div className="kpi-value">{rules.length - verified || '—'}</div>
      </div>
    </div>

    <section className="panel">
      <h3 className="panel-title">
        <span>Adding a jurisdiction, a year, or a client</span>
        <span className="right">what it actually takes</span>
      </h3>
      <p className="small muted">
        The table below is the answer to &ldquo;is this Georgia-only?&rdquo;.{' '}
        {rules.length} programs are codified
        {yearScoped != null && <> and {yearScoped} {yearScoped === 1 ? 'has' : 'have'} statute
        authored by tax year so far</>}; the rest are described but refuse to
        calculate, by name, until someone authors their statute. Nothing about the
        engine is Georgia-specific.
      </p>
      <ul className="cov-engagements">
        <li>
          <b>New tax year</b>
          <span className="cov-scope cov-scope-in_scope">one file</span>
          <em>
            A complete rule file for that year — not a base plus overrides merged
            at run time. The question an authority asks is &ldquo;what rules did
            you apply to my 2021 return?&rdquo;, and the answer has to be a file
            with a fingerprint.
          </em>
        </li>
        <li>
          <b>New program or jurisdiction</b>
          <span className="cov-scope cov-scope-in_scope">one rule file</span>
          <em>
            A rule file for the programme, registered once. Federal is the same
            shape — the level of government is a field, not a separate code path.
          </em>
        </li>
        <li>
          <b>New client</b>
          <span className="cov-scope cov-scope-in_scope">no code at all</span>
          <em>
            Their payroll lands in the lakehouse under their own account, they
            appear in the client selector, and every calculating screen re-prices
            for them.
          </em>
        </li>
      </ul>
      <p className="small muted">
        Statute lives in git rather than a database on purpose: a change to what
        the law says should arrive as a reviewable diff, not an UPDATE nobody saw.
      </p>
    </section>

    <section className="panel">
      <h3 className="panel-title">
        <span><BookOpenCheck size={15} /> Programs</span>
        <span className="right">each claim bound to its year&apos;s rules</span>
      </h3>
      <FilterBar {...table.bar('programs')} />
      <table className="tbl">
        <thead>
          <tr>
            <SortHeader {...table.head('name')} />
            <SortHeader {...table.head('jurisdiction')} />
            <SortHeader {...table.head('citation')} />
            <SortHeader {...table.head('years')} />
            <SortHeader {...table.head('filing')} />
            <SortHeader {...table.head('threshold')} className="num" />
            <SortHeader {...table.head('benefit')} className="num" />
            <SortHeader {...table.head('review')} />
          </tr>
        </thead>
        <tbody>
          {table.rows.map((r) => {
            const years = authoredYearsLabel(yearsFor(r.code));
            return (
              <tr key={r.code}>
                <td>{r.name}</td>
                <td>{r.jurisdiction}</td>
                <td className="small"><code>{r.citation}</code></td>
                <td className="small">
                  {years
                    ? years
                    : programs ? <span className="muted">no authored years — not calculated</span> : '—'}
                </td>
                <td className="small">{r.filing?.window || '—'}</td>
                <td className="num">{r.threshold ?? '—'}</td>
                <td className="num">{r.benefit_period_years ?? '—'}</td>
                <td>
                  {r.verified
                    ? <span className="pill pill-ok" title={`${r.verification?.verified_by || ''} ${r.verification?.verified_at || ''}`}><ShieldCheck size={11} /> signed</span>
                    : <span className="pill pill-neutral">pending</span>}
                </td>
              </tr>
            );
          })}
          {!rules.length && !loading && (
            <tr><td colSpan={8} className="muted">No rule packs loaded.</td></tr>
          )}
        </tbody>
      </table>
    </section>
  </>;
}
