/**
 * The top navigation's groups, built from the app's NAV.
 *
 * The section names become the groups. An entry that needs a client is
 * DISABLED WITH A REASON while none is selected, never hidden: a missing entry
 * says "this product does not do that"; a disabled one says "not yet".
 *
 * `nav` is passed in rather than imported so this stays free of React and of
 * App.jsx (which imports it).
 */
export const NEEDS_CLIENT_REASON = 'Pick a client first';

export function navGroups(nav, { hasClient }) {
  return nav.map((group) => ({
    section: group.section,
    items: group.items.map((item) => ({
      id: item.id,
      label: item.label,
      icon: item.icon,
      disabled: Boolean(item.needsClient) && !hasClient,
      reason: item.needsClient && !hasClient ? NEEDS_CLIENT_REASON : undefined,
      sealed: Boolean(item.sealed),
    })),
  }));
}

/** The group an item belongs to, so the bar can mark where you are. */
export function groupOf(nav, id) {
  return nav.find((group) => group.items.some((item) => item.id === id))?.section ?? null;
}
