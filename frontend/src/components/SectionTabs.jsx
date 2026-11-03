import Tabs from './ui/Tabs.jsx';

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
    <Tabs
      className="section-tabs"
      tabs={tabs}
      active={active}
      onChange={onChange}
      label={label}
      idPrefix={idPrefix}
    />
  );
}

/**
 * The panel half. `keepMounted` keeps a visited panel alive while hidden, so
 * returning to it costs neither a refetch nor its expand and sort state.
 *
 * With a `label` it is a named region rather than a tabpanel: the client page
 * switches sections with a stepper of links, and a tabpanel with no tab
 * pointing at it would be a role that promises a control that is not there.
 */
export function SectionTabPanel({
  id, active, idPrefix = 'section', keepMounted = false, visited = true, label = null, children,
}) {
  const shown = id === active;
  if (!shown && !(keepMounted && visited)) return null;
  if (label) {
    return (
      <div role="region" id={`${idPrefix}-panel-${id}`} aria-label={label} hidden={!shown}>
        {children}
      </div>
    );
  }
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
