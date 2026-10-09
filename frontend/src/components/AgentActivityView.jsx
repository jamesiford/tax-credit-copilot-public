import { useCallback, useEffect, useState } from 'react';
import {
  CheckCircle2, Flag, Loader2, RotateCcw, ShieldQuestion, Undo2,
} from 'lucide-react';
import { fetchFindings, fetchMe, reopenFinding, resolveFinding } from '../api.js';
import { PORTFOLIO } from '../lib/scopeDimension.js';
import { USD } from '../lib/coverage.js';

/**
 * Agent Activity — what an agent found, and what you decided about it.
 *
 * Replaces the Agent Workbench, which listed registered agents and their
 * status. That is topology: it shows how the software is arranged, which is
 * exactly what the editorial test cuts. Nobody filing a return needs to know
 * that `HeadcountAgent` is registered.
 *
 * A finding is different. "This employee is counted at two worksites in the
 * same month" changes Average Headcount, which changes a number on a filed
 * return. It is a judgement, it has to reach a human, and the answer has to
 * come back and stick.
 *
 * The proposal is deliberately a starting point rather than an action. The
 * whole reason a finding exists is that a person has to choose — an agent that
 * silently applied its own proposal would be making the decision while
 * appearing to ask.
 */

function Decision({ finding, onDecide, busy }) {
  const [worksite, setWorksite] = useState(
    finding.evidence?.units?.[0]?.worksite_id || '',
  );

  if (finding.resolution) {
    return (
      <div className="finding-decided">
        <CheckCircle2 size={14} />
        <b>{finding.resolution.resolution}</b>
        {finding.resolution.detail?.keep_worksite && (
          <span>kept at {finding.resolution.detail.keep_worksite}</span>
        )}
        <em>{finding.resolution.decided_by}</em>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={busy}
          onClick={() => onDecide(finding, { reopen: true })}
        >
          <Undo2 size={13} /> Reopen
        </button>
      </div>
    );
  }

  const units = finding.evidence?.units || [];

  return (
    <div className="finding-actions">
      {finding.proposes === 'assign' && units.length > 0 && (
        <label className="finding-pick">
          <span>Count at</span>
          <select value={worksite} onChange={(e) => setWorksite(e.target.value)}>
            {units.map((u) => (
              <option key={u.worksite_id} value={u.worksite_id}>
                {u.worksite_id} · {u.hours}h · {USD.format(u.wages)}
              </option>
            ))}
          </select>
        </label>
      )}
      <button
        type="button"
        className="btn btn-primary"
        disabled={busy}
        onClick={() => onDecide(finding, {
          resolution: finding.proposes,
          keep_worksite: finding.proposes === 'assign' ? worksite : undefined,
        })}
      >
        {finding.proposes === 'assign' ? 'Assign' : 'Drop'}
      </button>
      <button
        type="button"
        className="btn btn-secondary"
        disabled={busy}
        onClick={() => onDecide(finding, { resolution: 'accept' })}
        title="Leave the data as it is — the double count or short period is real."
      >
        Leave as is
      </button>
      <button
        type="button"
        className="btn btn-secondary"
        disabled={busy}
        onClick={() => onDecide(finding, { resolution: 'flag' })}
        title="Cannot decide yet — needs the client."
      >
        <Flag size={13} /> Ask client
      </button>
    </div>
  );
}

export default function AgentActivityView({ scope, scopeOptions }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null);

  const isPortfolio = scope.clientId === PORTFOLIO;
  const jurisdiction = (scopeOptions?.programs || [])
    .find((p) => p.program_code === scope.programCode)?.jurisdiction?.code || null;

  const load = useCallback(async () => {
    if (isPortfolio || scope.year == null) { setLoading(false); return; }
    setLoading(true);
    setError(null);
    try {
      setData(await fetchFindings(scope.clientId, scope.year, jurisdiction));
    } catch (reason) {
      setError(String(reason));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [isPortfolio, scope.clientId, scope.year, jurisdiction]);

  useEffect(() => { load(); }, [load]);

  // Who is deciding, as the API knows them. Unknown leaves attribution to the
  // server, which uses the token when there is one.
  const [me, setMe] = useState(null);
  useEffect(() => {
    let live = true;
    fetchMe().then((who) => { if (live) setMe(who); }).catch(() => { if (live) setMe(null); });
    return () => { live = false; };
  }, []);

  const decide = async (finding, { resolution, keep_worksite, reopen }) => {
    setBusy(finding.finding_id);
    setError(null);
    try {
      const body = {
        client_id: scope.clientId,
        tax_year: scope.year,
        resolution: resolution || 'accept',
        keep_worksite,
        ...(me?.upn ? { decided_by: me.upn } : {}),
      };
      if (reopen) await reopenFinding(finding.finding_id, body);
      else await resolveFinding(finding.finding_id, body);
      await load();
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(null);
    }
  };

  if (isPortfolio) {
    return <>
      <Header />
      <div className="callout info">
        Findings are per client-year, because a judgement about one employee&apos;s
        worksites belongs to one client. Select a client to review theirs.
      </div>
    </>;
  }

  const summary = data?.summary;

  return <>
    <Header />

    {error && <div className="callout warn">{error}</div>}
    {loading && !data && (
      <div className="callout info"><Loader2 size={15} className="spin" /> Looking…</div>
    )}

    {summary && (
      <div className="kpi-strip tcc-kpi-4">
        <div className={`kpi-card ${summary.requires_decision ? 'amber' : ''}`}>
          <div className="kpi-label">Awaiting a decision</div>
          <div className="kpi-value">{summary.requires_decision || '—'}</div>
          <div className="kpi-sub">nobody has answered these yet</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Decisions</div>
          <div className="kpi-value">{summary.total}</div>
          <div className="kpi-sub">
            covering {(summary.instances || summary.total).toLocaleString()} instances
          </div>
        </div>
        <div className={`kpi-card ${summary.all_decided ? 'green' : ''}`}>
          <div className="kpi-label">Status</div>
          <div className="kpi-value">
            {summary.none_found ? 'Nothing found' : summary.all_decided ? 'All answered' : 'Open'}
          </div>
          <div className="kpi-sub">
            {summary.none_found
              ? 'the agent looked and found nothing'
              : summary.all_decided
                ? 'every finding has a recorded decision'
                : 'unanswered findings affect the figures'}
          </div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Kinds</div>
          <div className="kpi-value">{Object.keys(summary.by_kind || {}).length || '—'}</div>
          <div className="kpi-sub">{Object.keys(summary.by_kind || {}).join(', ') || 'none'}</div>
        </div>
      </div>
    )}

    {data && data.findings.length === 0 && (
      <div className="callout info">
        <CheckCircle2 size={15} />
        <b>The agent found nothing for this client-year.</b> That is a result, not
        an absence — the checks ran and came back clean.
      </div>
    )}

    {(data?.findings || []).map((finding) => (
      <section className={`panel finding ${finding.requires_decision ? 'open' : 'closed'}`} key={finding.finding_id}>
        <h3 className="panel-title">
          <span>
            <ShieldQuestion size={15} /> {finding.title}
          </span>
          <span className="right">
            {finding.grain === 'policy'
              ? `policy · ${finding.population.instances.toLocaleString()} instances`
              : finding.employee_id}
          </span>
        </h3>
        <p className="small">{finding.why_it_matters}</p>

        {finding.population && (
          <div className="tcc-control-grid finding-evidence">
            <div>
              <span>Instances</span>
              <b>{finding.population.instances.toLocaleString()}</b>
              <small>one decision covers all</small>
            </div>
            <div>
              <span>Employees</span>
              <b>{finding.population.employees_affected.toLocaleString()}</b>
              <small>affected</small>
            </div>
            <div>
              <span>Wages involved</span>
              <b>{USD.format(finding.population.total_wages)}</b>
              <small>{Math.round(finding.population.total_hours).toLocaleString()} hours</small>
            </div>
          </div>
        )}

        {(finding.evidence?.units || []).length > 0 && (
          <div className="tcc-control-grid finding-evidence">
            {finding.evidence.units.map((u) => (
              <div key={u.worksite_id}>
                <span>{u.worksite_id}</span>
                <b>{u.hours}h</b>
                <small>{USD.format(u.wages)} · {u.periods} period{u.periods === 1 ? '' : 's'}</small>
              </div>
            ))}
          </div>
        )}

        {finding.population?.sample?.length > 0 && (
          <details className="tcc-detail-block">
            <summary>
              {finding.population.sample.length} example
              {finding.population.sample.length === 1 ? '' : 's'} of{' '}
              {finding.population.sample_of.toLocaleString()}
            </summary>
            <ul className="finding-sample">
              {finding.population.sample.map((s, i) => (
                <li key={`${s.employee_id}-${s.pay_date || s.month}-${i}`}>
                  <b>{s.employee_id}</b>
                  <span>{s.month || s.pay_date}</span>
                  {s.worksite_id && <span>{s.worksite_id}</span>}
                  {s.hours != null && <span>{s.hours}h</span>}
                  {s.wages != null && <span>{USD.format(s.wages)}</span>}
                </li>
              ))}
            </ul>
            <p className="small muted">
              A sample, not the list. Reviewing {finding.population.sample_of.toLocaleString()} rows
              one at a time is not review — the pattern is what you are deciding about.
            </p>
          </details>
        )}

        <p className="small muted">
          <b>Proposed:</b> {finding.proposed_effect} Nothing is applied until you decide.
        </p>

        <Decision finding={finding} onDecide={decide} busy={busy === finding.finding_id} />
      </section>
    ))}
  </>;
}

function Header() {
  return (
    <div className="page-header tcc-page-header">
      <div>
        <div className="tcc-eyebrow">What needs a decision</div>
        <h1 className="page-title">Agents</h1>
        <div className="page-sub">
          What the agents found, and what you decided about it. Every finding
          changes a figure if left unanswered — nothing is applied automatically.
        </div>
      </div>
    </div>
  );
}
