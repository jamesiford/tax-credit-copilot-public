import { METHODS } from '../lib/trendGrid.js';

/**
 * Min-Max or Pay Period, as a control rather than a URL parameter.
 *
 * The two methods are not expected to agree — 539 against 656 eligible on the
 * reference client — and the statute has not chosen between them. A page that
 * shows one reading without saying the other exists presents a method choice as
 * a fact, which is why this is never hidden in a link.
 */
export default function MethodTabs({ method, onChange, label = 'Reading' }) {
  return (
    <div className="method-tabs" role="group" aria-label="Statutory reading">
      <span className="method-tabs-label">{label}</span>
      {METHODS.map(([value, text]) => (
        <button
          key={value}
          type="button"
          className={method === value ? 'active' : ''}
          aria-pressed={method === value}
          onClick={() => onChange(value)}
        >
          {text}
        </button>
      ))}
      <span className="method-tabs-note" title="The statute has not chosen between them">
        not expected to agree
      </span>
    </div>
  );
}
