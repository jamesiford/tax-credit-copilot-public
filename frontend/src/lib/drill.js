/**
 * The drill, resolved against the current route.
 *
 * Portfolio -> Client -> Location -> Eligibility -> Employee. The partner's own
 * framing of the product is an accordion in which "at every level the user
 * remains only one or two clicks away from the supporting detail"; the trail
 * under the top bar is that shape, on screen from the first second.
 *
 * ## The rule that makes the drill work
 *
 * An unreached rung must read as **"you haven't got here yet"**, never as
 * **"this is broken"**. Three things carry that distinction:
 *
 *   - a REACHED rung shows the real name ("Ironbridge Logistics", not the
 *     generic word "Client");
 *   - the CURRENT rung is marked;
 *   - an unreached rung is dimmed, is NOT a button, and says what to do next.
 *
 * Rendered as greyed-out buttons it looks like a half-built app, which is the
 * one impression this ladder exists to prevent.
 *
 * It is derived from the ROUTE, never from separate state, so the trail and the
 * page beside it cannot disagree about where you are. This used to live in
 * `SideRail`, which it replaces; the rules and the labels are carried over
 * unchanged.
 *
 * `eligibility` is the rung between Location and Employee: the employee cohort
 * for a client-year. It is a nav destination rather than a route segment, so it
 * is "reached" when it is the active view.
 */
export function drillRungs({ clientId, clientName, unitId, token, view }) {
  const hasClient = clientId != null && clientId !== 'portfolio';
  const onEligibility = view === 'eligibility';

  return [
    {
      key: 'portfolio',
      label: 'Portfolio',
      reached: true,
      current: !hasClient && !onEligibility,
      hint: null,
    },
    {
      key: 'client',
      label: hasClient ? (clientName || `Account ${clientId}`) : 'Client',
      reached: hasClient,
      current: hasClient && !unitId && !token && !onEligibility,
      hint: 'pick a client from the book',
    },
    {
      key: 'unit',
      label: unitId || 'Location',
      reached: Boolean(unitId),
      current: Boolean(unitId) && !token,
      hint: 'open a year on a location',
    },
    {
      key: 'eligibility',
      label: 'Eligibility',
      reached: hasClient,
      current: onEligibility,
      hint: 'pick a client first',
    },
    {
      key: 'employee',
      label: 'Employee',
      reached: Boolean(token),
      current: Boolean(token),
      hint: 'open an employee\u2019s walk',
    },
  ];
}

/**
 * True when nothing below the book has been reached: the trail collapses to one
 * quiet line rather than paying for five rungs that all say "not yet".
 */
export function atPortfolio(rungs) {
  return rungs.every((rung) => rung.key === 'portfolio' || !rung.reached);
}
