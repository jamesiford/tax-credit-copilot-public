/*
 * Why: when part of a page's data is down, the page still answers with the rest, and it says
 * exactly what is missing and what to do. Silence here reads as "nothing found".
 * Never: hide an entry, invent a reason, or call an unreachable store an empty one.
 */
import Callout from './Callout.jsx';

export default function DegradedBanner({ degraded }) {
  const items = Array.isArray(degraded) ? degraded.filter((d) => d && d.dependency) : [];
  if (!items.length) return null;
  return (
    <div role="status" className="degraded-banner">
      <Callout
        tone="partial"
        title={items.length === 1 ? 'Part of this page is unavailable' : `${items.length} parts of this page are unavailable`}
      >
        <ul>
          {items.map((d) => (
            <li key={`${d.dependency}:${d.impact}`}>
              <b>{d.dependency}</b>: {d.impact} <span>{d.remedy}</span>
            </li>
          ))}
        </ul>
      </Callout>
    </div>
  );
}
