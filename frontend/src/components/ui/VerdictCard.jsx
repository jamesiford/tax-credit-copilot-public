/*
 * Why: wherever the product states a verdict (a programme, a year, a finding)
 * it should look the same and read in the same order: who it is about, what the
 * verdict is, why, and where to see the working. The border carries the
 * reading; the pill carries it again in words and a glyph, so colour is never
 * the only signal.
 * Never: invent a verdict or a derivation. `assessment` is text the caller
 * already holds (the calculation trail's own sentence); with none, the callout
 * is omitted. A verdict is never the selection blue.
 */
import { Link } from 'react-router-dom';
import Callout from './Callout.jsx';
import Card from './Card.jsx';
import Pill from './Pill.jsx';

function Details({ details }) {
  if (!details) return null;
  const label = `${details.label || 'Details'} \u2192`;
  if (details.to) {
    return <Link className="tcc-verdict-more" to={details.to}>{label}</Link>;
  }
  if (details.onClick) {
    return (
      <button type="button" className="tcc-verdict-more tcc-link" onClick={details.onClick}>
        {label}
      </button>
    );
  }
  return null;
}

export default function VerdictCard({
  tone = 'neutral',
  pills = [],
  title,
  assessmentTitle = 'Why',
  assessment = null,
  details = null,
  level = 3,
  className = '',
  children,
}) {
  // The heading level is the page's to choose: a card under an h1 is an h2.
  const Heading = `h${Math.min(Math.max(Number(level) || 3, 2), 6)}`;
  return (
    <Card as="article" tone={tone} label={title} className={['tcc-verdict', className].filter(Boolean).join(' ')}>
      {pills.length ? (
        <div className="tcc-verdict-pills">
          {pills.map((pill) => (
            <Pill key={pill.label} variant={pill.variant} icon={pill.icon}>{pill.label}</Pill>
          ))}
        </div>
      ) : null}
      <Heading className="tcc-verdict-title">{title}</Heading>
      {assessment ? <Callout title={assessmentTitle} tone={tone}>{assessment}</Callout> : null}
      {children}
      <Details details={details} />
    </Card>
  );
}
