/*
 * Why: every screen that shows a program's lifecycle or a draft's status uses the same pill, so a word means one thing.
 * Never: carry a verdict. `calculable` says the engine can price it; it never says the statute is right.
 */
import Pill from '../ui/Pill.jsx';
import { DRAFT_STATUS_LABEL, DRAFT_STATUS_PILL, LIFECYCLE_LABEL, LIFECYCLE_PILL } from '../../lib/programs.js';

export function LifecycleBadge({ lifecycle }) {
  return <Pill variant={LIFECYCLE_PILL[lifecycle] || 'neutral'}>{LIFECYCLE_LABEL[lifecycle] || lifecycle || '—'}</Pill>;
}

export function DraftStatusBadge({ status }) {
  return <Pill variant={DRAFT_STATUS_PILL[status] || 'neutral'}>{DRAFT_STATUS_LABEL[status] || status}</Pill>;
}

/** The "not verified" mark that sits beside any statutory value or year. */
export function NotVerified({ children = 'Not verified' }) {
  return <Pill variant="partial" tone="outline">{children}</Pill>;
}
