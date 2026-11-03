import { isExpired } from '../../lib/evidence.js';
import Button from '../ui/Button.jsx';
import Card from '../ui/Card.jsx';
import EvidenceBlocks from './EvidenceBlocks.jsx';

/**
 * The write-flow extension point: what WOULD be recorded, and two buttons.
 *
 * It is inert until the backend emits an evidence item with
 * `kind: "confirmation"`, and even then it does nothing by itself: Confirm and
 * Cancel call the callbacks it is given, and with no `onConfirm` the Confirm
 * button is disabled and says so rather than looking like it works.
 *
 * Every write lands on a number on a filed return, so the preview is the
 * platform's own blocks, verbatim, and an expired confirmation cannot be
 * confirmed. `now` is injectable so expiry is testable.
 *
 * Never: confirm on a timer, confirm without a click, or compute the preview.
 */
export default function ConfirmCard({ item, onConfirm, onCancel, now = Date.now(), busy = false }) {
  const confirmation = item.confirmation;
  const expired = isExpired(confirmation, now);
  const connected = typeof onConfirm === 'function';

  return (
    <Card as="article" tone="partial" title={item.title || 'Confirm'} className="ask-confirm">
      {confirmation.summary ? <p className="ask-text">{confirmation.summary}</p> : null}
      <EvidenceBlocks blocks={confirmation.blocks} />
      {confirmation.expires_at ? (
        <p className="ask-note" data-expired={expired || undefined}>
          {expired ? `Expired at ${confirmation.expires_at}. Ask again to get a fresh one.` : `Expires at ${confirmation.expires_at}.`}
        </p>
      ) : null}
      {connected ? null : (
        <p className="ask-note">Confirming is not connected in this build, so nothing can be recorded from here.</p>
      )}
      <div className="ask-confirm-actions">
        <Button
          variant="primary"
          disabled={!connected || expired}
          loading={busy}
          onClick={() => onConfirm?.(item)}
        >
          {confirmation.confirm_label}
        </Button>
        <Button variant="secondary" onClick={() => onCancel?.(item)}>
          {confirmation.cancel_label}
        </Button>
      </div>
    </Card>
  );
}
