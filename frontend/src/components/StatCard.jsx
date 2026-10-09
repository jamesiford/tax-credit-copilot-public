/**
 * One figure, one treatment.
 *
 * There were three KPI card styles across four pages — a thick coloured top
 * border on the portfolio, two DIFFERENT rows on the client page, and a thin
 * left border on the unit page. Same job, three answers.
 *
 * `tone` encodes the READING, not the topic. Blue previously marked Exposure,
 * Cells assessed and Unverified — three unrelated things — while green marked
 * Recoverable, so colour carried no information. Anything without a reading is
 * neutral.
 */
export default function StatCard({ label, value, sub, tone = 'neutral', empty = false }) {
  // An absent value should recede, not compete: "—" rendered at the weight of
  // $416,535 says the two are comparable.
  const cls = ['tcc-stat', `tcc-stat-${empty ? 'empty' : tone}`].join(' ');
  return (
    <div className={cls}>
      <div className="tcc-stat-label">{label}</div>
      <div className="tcc-stat-value">{empty ? '—' : value}</div>
      {sub ? <div className="tcc-stat-sub">{sub}</div> : null}
    </div>
  );
}

/** The row they sit in. Keeps the grid in one place rather than per page. */
export function StatRow({ children }) {
  return <div className="tcc-stat-row">{children}</div>;
}
