/**
 * Two peer grids answering different questions about one scope.
 *
 * The visual language is `MethodTabs` — deliberately the same control, because
 * a third tab style would make "which of these is a tab" a thing a reader has
 * to work out. What differs is the job: MethodTabs picks a statutory READING of
 * the same population, this picks WHICH population is on screen.
 *
 * The count is part of the label, not decoration. "Who to call" does not tell
 * you whether to click; "Who to call (4)" does, and "(0)" saves the click
 * altogether.
 */
export default function GridTabs({ tabs, active, onChange, label = 'View' }) {
  return (
    <div className="method-tabs grid-tabs" role="tablist" aria-label={label}>
      <span className="method-tabs-label">{label}</span>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          id={`grid-tab-${tab.id}`}
          aria-selected={active === tab.id}
          aria-controls={`grid-panel-${tab.id}`}
          className={active === tab.id ? 'active' : ''}
          onClick={() => onChange(tab.id)}
          title={tab.hint}
        >
          {tab.label}
          {tab.count == null ? null : <span className="grid-tab-count">{tab.count}</span>}
        </button>
      ))}
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
