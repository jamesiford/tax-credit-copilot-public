/*
 * Why: one program in full: what blocks calculation, the pack's own metadata, each authored year with whether it is still flagged
 * unverified and where its values came from, and the validator's findings. Everything is read from the registry and the packs.
 * Never: say any year is verified; the catalog reports what is encoded, not that it is right.
 */
import { useEffect, useState } from 'react';
import { fetchProgram } from '../../api.js';
import PageHeader from '../PageHeader.jsx';
import Callout from '../ui/Callout.jsx';
import Card from '../ui/Card.jsx';
import EmptyState from '../ui/EmptyState.jsx';
import Skeleton from '../ui/Skeleton.jsx';
import { engagementLabel } from '../../lib/programs.js';
import { LifecycleBadge, NotVerified } from './Badges.jsx';
import UnverifiedNotice from './UnverifiedNotice.jsx';

function Years({ years }) {
  if (!years.length) return <p className="small muted">No year pack is authored, so this program is described and cannot be calculated (ADR-005).</p>;
  return (
    <table className="tbl-compact" aria-label="Authored years">
      <thead><tr><th>Tax year</th><th>Pack version</th><th>Status</th><th>Source</th><th>Findings</th></tr></thead>
      <tbody>
        {years.map((y) => {
          const errors = y.issues.filter((i) => i.severity === 'error').length;
          return (
            <tr key={y.tax_year}>
              <td>{y.tax_year}</td>
              <td className="small"><code>{y.rule_pack_version || '—'}</code></td>
              <td>{y.unverified ? <NotVerified>Not verified: flagged in the pack</NotVerified> : <NotVerified>Not verified: no flag in the pack</NotVerified>}</td>
              <td className="small">{y.source || '—'}</td>
              <td className="small">{errors ? `${errors} error${errors === 1 ? '' : 's'}` : 'No errors'}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export default function ProgramDetail({ code, onBack }) {
  const [state, setState] = useState({ loading: true, data: null, error: null });
  useEffect(() => {
    let cancelled = false;
    setState({ loading: true, data: null, error: null });
    fetchProgram(code)
      .then((data) => {
        // An answer with no pack or validation is not a program: say so instead of drawing a page of blanks.
        if (!data?.pack || !data?.validation) throw new Error('The registry answered with nothing the page can show.');
        if (!cancelled) setState({ loading: false, data, error: null });
      })
      .catch((error) => { if (!cancelled) setState({ loading: false, data: null, error }); });
    return () => { cancelled = true; };
  }, [code]);

  const back = { label: 'All programs', onClick: onBack };
  if (state.loading) return <><PageHeader eyebrow="Program manager" title={code} back={back} /><Skeleton lines={5} label="Reading the program" /></>;
  if (state.error) {
    return (
      <><PageHeader eyebrow="Program manager" title={code} back={back} />
        <EmptyState title={state.error.status === 404 ? 'No such program' : 'The program is unavailable'}>
          {state.error.status === 404 ? `${code} is not in the registry.` : state.error.message} Nothing was changed.
        </EmptyState></>
    );
  }
  const p = state.data;
  const errors = p.validation.pack.filter((i) => i.severity === 'error');
  return (
    <>
      <PageHeader
        eyebrow="Program manager" title={p.name} back={back} sub={p.pack.citation || 'No citation recorded'}
        meta={[{ label: 'Code', value: p.code }, { label: 'State', value: p.state || p.jurisdiction.level }, { label: 'Pack', value: p.pack.file }]}
        actions={<LifecycleBadge lifecycle={p.lifecycle} />}
      />
      <UnverifiedNotice />
      {p.blockers.length ? (
        <Callout tone="partial" title="What blocks calculation">
          <ul>{p.blockers.map((b) => <li key={b}>{b}</li>)}</ul>
        </Callout>
      ) : <Callout tone="neutral" title="Calculable for its authored years"><p>The engine can price this program for the years below. That says nothing about whether its values are right.</p></Callout>}
      <div className="prog-stack">
        <Card title="Pack" subtitle={`Credit model ${p.pack.engine_profile.credit_model}, headcount ${p.pack.engine_profile.headcount_model}`}>
          <dl className="small">
            <dt>Credit</dt><dd>{p.pack.credit_name || '—'}</dd>
            <dt>Pack version</dt><dd><code>{p.pack.rule_pack_version || '—'}</code></dd>
            <dt>Engagement</dt><dd>{engagementLabel(p.engagement)}</dd>
          </dl>
        </Card>
        <Card title="Tax years" subtitle={`${p.years.length} authored`}><Years years={p.years} /></Card>
        <Card title="Validation" subtitle={p.validation.valid ? 'No errors (valid is not verified)' : `${p.validation.error_count} error(s)`}>
          {errors.length ? <ul className="prog-findings">{errors.map((i, n) => <li key={n}><code>{i.path}</code> {i.message}</li>)}</ul> : <p className="small muted">The base pack has no errors.</p>}
        </Card>
      </div>
    </>
  );
}
