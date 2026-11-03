import './KpiTile.css';

/**
 * One figure, one treatment: a large centred number over a small caption on a
 * tinted tile.
 *
 * This is the ONLY stat tile (it replaced `StatCard`/`StatRow`, which had
 * already replaced three older ones). `tone` encodes the READING and is drawn
 * from the --state-* families, never a free colour: `above-min` / `below-min`
 * / `partial` / `base-year` / `neutral`. Anything without a reading is neutral,
 * so colour on a tile always means something.
 *
 * Never: compute the value (it renders what it is given, as a string, so money
 * stays exact), tint a tile by topic, or show an absent figure at the weight of
 * a real one. `empty` draws a dashed, receding tile with an em dash.
 */
const TONES = ['neutral', 'above-min', 'below-min', 'partial', 'base-year'];

export default function KpiTile({ label, value, sub, tone = 'neutral', empty = false }) {
  const kind = empty ? 'empty' : (TONES.includes(tone) ? tone : 'neutral');
  return (
    <div className={`ui-kpi ui-kpi-${kind}`}>
      <div className="ui-kpi-value">{empty ? '—' : value}</div>
      <div className="ui-kpi-label">{label}</div>
      {sub ? <div className="ui-kpi-sub">{sub}</div> : null}
    </div>
  );
}

/** The row they sit in, so the grid lives in one place rather than per page. */
export function KpiRow({ children, label }) {
  return <div className="ui-kpi-row" role="group" aria-label={label}>{children}</div>;
}
