/*
 * Why: step 4 shows what the draft would calculate on the committed synthetic sample, labelled on screen, in the table caption
 * and beside every year: "Preview, not verified, not for filing". It writes nothing and stores nothing; running it twice is safe.
 * Never: drop the label, present a figure without the draft's unverified-flag count, or offer a client's payroll here.
 */
import { useState } from 'react';
import { previewProgramDraft } from '../../api.js';
import { PREVIEW_LABEL } from '../../lib/programs.js';
import Button from '../ui/Button.jsx';
import Callout from '../ui/Callout.jsx';
import Card from '../ui/Card.jsx';
import EmptyState from '../ui/EmptyState.jsx';
import Skeleton from '../ui/Skeleton.jsx';

const money = (n) => `$${Number(n).toLocaleString('en-US', { maximumFractionDigits: 0 })}`;

function Result({ result }) {
  return (
    <>
      <p className="prog-preview-label" role="status">{result.label || PREVIEW_LABEL}</p>
      <p className="small">{result.dataset.description}. {result.unverified_flags} statutory block{result.unverified_flags === 1 ? '' : 's'} still carry the unverified flag. Nothing was written or stored.</p>
      <table className="tbl-compact prog-numbers" aria-label="Preview, not verified, not for filing">
        <caption className="ui-visually-hidden">{PREVIEW_LABEL}</caption>
        <thead>
          <tr><th>Tax year</th><th className="num">Average headcount</th><th className="num">Prior year</th><th className="num">Net-new jobs</th><th className="num">Credit per job</th><th className="num">Annual credit</th></tr>
        </thead>
        <tbody>
          {result.years.map((y) => (
            <tr key={y.tax_year}>
              <td>{y.tax_year}{y.is_base_year ? ' (base year)' : ''}</td>
              <td className="num">{y.average_headcount}</td>
              <td className="num">{y.prior_average_headcount ?? '\u2014'}</td>
              <td className="num">{y.qualifying_jobs}</td>
              <td className="num">{money(y.per_job_usd)}</td>
              <td className="num">{money(y.annual_credit_usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {result.declined.length ? (
        <Callout title="Not previewed">
          <ul>{result.declined.map((d) => <li key={d.tax_year}>{d.tax_year}: {d.detail}</li>)}</ul>
        </Callout>
      ) : null}
      {!result.years.length ? <EmptyState title="Nothing could be priced">The sample holds no payroll for the years in this draft.</EmptyState> : null}
    </>
  );
}

export default function StepPreview({ draft, act }) {
  const [state, setState] = useState({ loading: false, result: null, error: null });
  const run = async () => {
    setState({ loading: true, result: null, error: null });
    try { setState({ loading: false, result: await act((id) => previewProgramDraft(id)), error: null }); }
    catch (error) { setState({ loading: false, result: null, error }); }
  };
  return (
    <Card title="Preview a calculation" subtitle={`${PREVIEW_LABEL}. On the committed synthetic sample payroll, in the draft's state.`}>
      <Callout tone="partial" title="Not verified, not for filing">
        <p>The figures are the engine pricing this draft&apos;s own numbers over generated payroll. They show whether the pack behaves; they say nothing about whether its statute values are right.</p>
      </Callout>
      <div className="prog-actions">
        <Button variant="primary" onClick={run} loading={state.loading} disabled={!draft.documents.years || !Object.keys(draft.documents.years).length}>Run the preview</Button>
      </div>
      {state.loading ? <Skeleton lines={4} label="Pricing the draft on the sample" /> : null}
      {state.error ? (
        <Callout tone="partial" title="The preview could not run"><p>{state.error.reason || state.error.message}</p>
          <p>Nothing was changed. Fix the findings on the pack and year steps, then try again.</p></Callout>
      ) : null}
      {state.result ? <Result result={state.result} /> : null}
    </Card>
  );
}
