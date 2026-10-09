/**
 * Sections of one page, one visible at a time.
 *
 * The employee walk had this as a hand-rolled row of buttons, and the client
 * page stacked its four sections instead, so What-if sat four and a half
 * screens below the grid it answers questions about. One component, so the two
 * pages cannot drift into two tab styles.
 *
 * Not `GridTabs`, on purpose. GridTabs switches which POPULATION a grid shows,
 * inside a page; this switches which QUESTION the page is answering, and it
 * sits at the top of the page as the page's own navigation.
 */
export default function SectionTabs({ tabs, active, onChange, label = 'Sections', idPrefix = 'section' }) {
  return (
    <div className="section-tabs" role="tablist" aria-label={label}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          id={`${idPrefix}-tab-${tab.id}`}
          aria-selected={active === tab.id}
          aria-controls={`${idPrefix}-panel-${tab.id}`}
          className={active === tab.id ? 'active' : ''}
          onClick={() => onChange(tab.id)}
          title={tab.hint}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

/**
 * The panel half. `keepMounted` keeps a visited panel alive while hidden, so
 * returning to it costs neither a refetch nor its expand and sort state.
 */
export function SectionTabPanel({ id, active, idPrefix = 'section', keepMounted = false, visited = true, children }) {
  const shown = id === active;
  if (!shown && !(keepMounted && visited)) return null;
  return (
    <div
      role="tabpanel"
      id={`${idPrefix}-panel-${id}`}
      aria-labelledby={`${idPrefix}-tab-${id}`}
      hidden={!shown}
    >
      {children}
    </div>
  );
}
