/*
 * Why: a count beside a nav entry or tab tells a reader where work is waiting.
 * The accessible name carries the full count; only the visible text is capped.
 * Never: cap the aria-label, render a bare "0" by accident, or use it for a
 * verdict (it is a tally, not a status).
 */
import './CountBadge.css';

export default function CountBadge({
  count,
  max = 99,
  label = '',
  showZero = false,
}) {
  const n = Number(count);
  if (!Number.isFinite(n) || (n === 0 && !showZero)) return null;

  const visible = n > max ? `${max}+` : String(n);
  const name = label ? `${n} ${label}` : String(n);

  return (
    <span className="ui-count-badge" aria-label={name} role="img">
      <span aria-hidden="true">{visible}</span>
    </span>
  );
}
