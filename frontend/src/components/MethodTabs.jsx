import { METHODS } from '../lib/trendGrid.js';
import Tabs from './ui/Tabs.jsx';

/**
 * Min-Max or Pay Period, as a control rather than a URL parameter.
 *
 * The two methods are not expected to agree — 539 against 656 eligible on the
 * reference client — and the statute has not chosen between them. A page that
 * shows one reading without saying the other exists presents a method choice as
 * a fact, which is why this is never hidden in a link.
 *
 * A thin wrapper over `ui/Tabs`: the choice is a selection, so it takes the
 * selection treatment, and there is no panel to point at.
 */
export default function MethodTabs({ method, onChange, label = 'Reading' }) {
  return (
    <div className="method-tabs">
      <span className="method-tabs-label" aria-hidden="true">{label}</span>
      <Tabs
        tabs={METHODS.map(([value, text]) => ({ id: value, label: text }))}
        active={method}
        onChange={onChange}
        label="Statutory reading"
        idPrefix="method"
        variant="segmented"
        controls={false}
      />
      <span className="method-tabs-note" title="The statute has not chosen between them">
        not expected to agree
      </span>
    </div>
  );
}
