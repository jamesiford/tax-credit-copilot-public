/*
 * Why: a placeholder with the shape of what is loading, so the page does not
 * jump and a reader is told something is coming rather than shown a blank.
 * Never: animate under prefers-reduced-motion, or stand in for a "nothing
 * found" answer once loading has finished.
 */
import './Skeleton.css';

export default function Skeleton({ lines = 3, label = 'Loading', className = '' }) {
  const count = Math.max(0, Math.floor(Number(lines)) || 0);

  return (
    <div
      className={['ui-skeleton', className].filter(Boolean).join(' ')}
      role="status"
      aria-busy="true"
      aria-live="polite"
    >
      <span className="ui-visually-hidden">{label}</span>
      {Array.from({ length: count }, (_, i) => (
        <div className="ui-skeleton-bar" key={i} aria-hidden="true" />
      ))}
    </div>
  );
}
