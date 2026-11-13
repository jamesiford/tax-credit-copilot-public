/*
 * Why: every change to a draft is an append-only audit event with its actor; this is the history a reviewer reads to see who
 * did what, in order. A draft with no history yet says so.
 * Never: reorder or hide events, or show a time without the actor.
 */
import Card from '../ui/Card.jsx';
import { DRAFT_STATUS_LABEL } from '../../lib/programs.js';

const EVENT_LABEL = {
  created: 'Created', edited: 'Edited', validated: 'Validated', review_requested: 'Review requested', approved: 'Approved for export',
  changes_requested: 'Changes requested', withdrawn: 'Withdrawn', exported: 'Exported',
};
const when = (iso) => (iso ? iso.replace('T', ' ').slice(0, 16) : '\u2014');

export default function DraftHistory({ events }) {
  return (
    <Card title="History" subtitle="Append-only: who did what, and when">
      {events?.length ? (
        <ol className="prog-history" aria-label="Draft history">
          {events.map((e) => (
            <li key={e.seq}>
              <b>{EVENT_LABEL[e.event_type] || e.event_type}</b> by {e.actor}, {when(e.at)}
              {e.to_status && e.to_status !== e.from_status ? ` (now ${DRAFT_STATUS_LABEL[e.to_status] || e.to_status})` : ''}
              {e.detail?.comment ? <> &mdash; &ldquo;{e.detail.comment}&rdquo;</> : null}
            </li>
          ))}
        </ol>
      ) : <p className="small muted">Nothing has happened to this draft yet.</p>}
    </Card>
  );
}
