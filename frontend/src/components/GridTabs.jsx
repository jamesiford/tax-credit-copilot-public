import Tabs from './ui/Tabs.jsx';

/**
 * Two peer grids answering different questions about one scope.
 *
 * Same control as `MethodTabs` (both wrap `ui/Tabs`), deliberately: a third tab style would make "which of these is a tab" a thing a reader has
 * to work out. What differs is the job: MethodTabs picks a statutory READING of
 * the same population, this picks WHICH population is on screen.
 *
 * The count is part of the label, not decoration. "Who to call" does not tell
 * you whether to click; "Who to call (4)" does, and "(0)" saves the click
 * altogether.
 */
export default function GridTabs({ tabs, active, onChange, label = 'View' }) {
  return (
    <div className="method-tabs grid-tabs">
      <span className="method-tabs-label" aria-hidden="true">{label}</span>
      <Tabs
        tabs={tabs}
        active={active}
        onChange={onChange}
        label={label}
        idPrefix="grid"
        variant="segmented"
      />
    </div>
  );
}

/** The panel half of the pair, so the tab and its content stay associated. */
export function GridTabPanel({ id, active, children }) {
  if (id !== active) return null;
  return (
    <div role="tabpanel" id={`grid-panel-${id}`} aria-labelledby={`grid-tab-${id}`}>
      {children}
    </div>
  );
}
