/*
 * Why: "Label: value · Label: value" is the compact way to state a record's
 * facts, and a definition list is what makes the pairing readable to a screen
 * reader. The separator is drawn by CSS so it is never read aloud.
 * Never: render a pair whose value is missing (a bare label reads as a claim),
 * or put the separator in the DOM.
 */
import './MetaLine.css';

const isPresent = (value) => value !== null && value !== undefined && value !== '';

export default function MetaLine({ items = [], className = '' }) {
  const shown = items.filter((item) => isPresent(item?.value));
  if (shown.length === 0) return null;

  return (
    <dl className={['ui-meta', className].filter(Boolean).join(' ')}>
      {shown.map(({ label, value }) => (
        <div className="ui-meta-item" key={label}>
          <dt className="ui-meta-label">{label}</dt>
          <dd className="ui-meta-value">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
