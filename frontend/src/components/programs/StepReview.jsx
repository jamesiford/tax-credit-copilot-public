/*
 * Why: step 5 is where a second person decides. Validation, the request for review and the decision are one place, with the
 * rule stated: the reviewer must differ from whoever wrote and submitted the draft where the deployment requires it, and approval
 * is for EXPORT only: it verifies nothing and activates nothing.
 * Never: enable a button the draft's allowed actions do not list, or describe approval as verification.
 */
import { useState } from 'react';
import { requestProgramReview, reviewProgramDraft, validateProgramDraft, withdrawProgramDraft } from '../../api.js';
import Button from '../ui/Button.jsx';
import Callout from '../ui/Callout.jsx';
import Card from '../ui/Card.jsx';
import { DraftStatusBadge } from './Badges.jsx';
import ValidationPanel from './ValidationPanel.jsx';

function Record({ review }) {
  if (!review.reviewer && !review.requested_by) return <p className="small muted">No review has been requested.</p>;
  return (
    <dl className="small">
      <dt>Requested by</dt><dd>{review.requested_by || '\u2014'}</dd>
      <dt>Decision</dt><dd>{review.decision ? `${review.decision === 'approve' ? 'Approved for export' : 'Changes requested'} by ${review.reviewer}` : 'Waiting for a reviewer'}</dd>
      {review.comment ? <><dt>Comment</dt><dd>{review.comment}</dd></> : null}
    </dl>
  );
}

export default function StepReview({ draft, act, stale }) {
  const [comment, setComment] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(null);
  const can = (action) => draft.allowed_actions.includes(action);
  const run = (name, call) => async () => {
    setBusy(name); setError(null);
    try { await act(call); setComment(''); } catch (reason) { setError(reason); } finally { setBusy(null); }
  };
  return (
    <div className="prog-grid-2">
      <Card title="Review" subtitle="Validate, ask for a second pair of eyes, record the decision" actions={<DraftStatusBadge status={draft.status} />}>
        <Callout title="What approval means">
          <p>Approving lets the bundle be exported for a person to commit. It does not verify any value and it activates nothing: a program becomes calculable only when its files are committed and deployed.</p>
        </Callout>
        {error ? <Callout tone="partial" title="That was refused"><p>{error.reason || error.message}</p></Callout> : null}
        <div className="prog-actions">
          <Button onClick={run('validate', (id) => validateProgramDraft(id))} loading={busy === 'validate'} disabled={!can('validate')}>Validate</Button>
          <Button variant="primary" onClick={run('request', (id) => requestProgramReview(id))} loading={busy === 'request'} disabled={!can('request_review')}>Request review</Button>
          <Button variant="ghost" onClick={run('withdraw', (id) => withdrawProgramDraft(id, comment))} loading={busy === 'withdraw'} disabled={!can('withdraw')}>Withdraw this draft</Button>
        </div>
        {!can('request_review') && can('validate') ? <p className="prog-field-note" role="status">Request review is available once the current documents validate with no errors.</p> : null}
        <h4>Reviewer&apos;s decision</h4>
        <label className="prog-field" htmlFor="review-comment"><span>Comment (required to request changes)</span>
          <textarea id="review-comment" value={comment} onChange={(e) => setComment(e.target.value)} rows={3} /></label>
        <div className="prog-actions">
          <Button variant="primary" onClick={run('approve', (id) => reviewProgramDraft(id, { decision: 'approve', comment }))} loading={busy === 'approve'} disabled={!can('approve')}>Approve for export</Button>
          <Button onClick={run('changes', (id) => reviewProgramDraft(id, { decision: 'request_changes', comment }))} loading={busy === 'changes'} disabled={!can('request_changes') || !comment.trim()}>Request changes</Button>
        </div>
        {!can('approve') ? <p className="prog-field-note" role="status">A decision is available once review has been requested.</p> : null}
        <Record review={draft.review} />
      </Card>
      <ValidationPanel validation={draft.validation} stale={stale} />
    </div>
  );
}
