/**
 * The client's review flow: which steps there are, where each one goes, and
 * which are unavailable and why.
 *
 * Six names were asked for (Position, Eligibility, Trend, At risk, Discovery,
 * Evidence). A step exists only where a place for it already does:
 *
 *   Position     the "What was claimed" section (`ctab=claimed`)
 *   Eligibility  the Eligibility view for this client
 *   Trend        the location grid (`ctab=location`, the default)
 *   At risk      "How am I doing" (`ctab=progress`): the year so far and the
 *                employees nearest the floor
 *   What-if      kept: it is an existing section and nothing else reaches it
 *   Evidence     the audit trail view
 *
 * Discovery has no view in this product, so it is omitted rather than invented.
 *
 * The flow is route-driven and never gates content: every enabled step is a
 * link, and a disabled one says WHY. `current` comes from the route, never
 * from state of its own, so the stepper cannot disagree with the page.
 */
import { DEFAULT_CLIENT_TAB } from './whatIf.js';

export const STEPS = [
  { id: 'claimed', label: 'Position', hint: 'What was claimed against what they were entitled to', kind: 'section' },
  { id: 'eligibility', label: 'Eligibility', hint: 'Who qualifies, employee by employee', kind: 'view' },
  { id: 'location', label: 'Trend', hint: 'Where credit is earned, location by location and year by year', kind: 'section' },
  { id: 'progress', label: 'At risk', hint: 'The year so far, and who is nearest the floor', kind: 'section' },
  { id: 'whatif', label: 'What-if', hint: 'What would change the answer', kind: 'section' },
  { id: 'evidence', label: 'Evidence', hint: 'The audit trail behind each figure', kind: 'view' },
];

//: Evidence reads the certified run, so it does not depend on this client
//: having a priceable year.
const NEEDS_A_YEAR = new Set(['claimed', 'eligibility', 'location', 'progress', 'whatif']);

/** Why the calculating steps are unavailable, or `null` when they are not. */
export function unavailableReason(clientScope) {
  if (!clientScope) return null; // still loading: never block on a read in flight
  const calculable = clientScope.calculable_years ?? clientScope.payroll_years ?? [];
  if (calculable.length) return null;
  const held = (clientScope.payroll_years || []).length > 0;
  return held
    ? 'Payroll is held for this client but no year overlaps an authored statute, so nothing can be calculated yet.'
    : 'No payroll is held for this client yet, so there is nothing to calculate.';
}

/** The URL a step goes to, given where the page is now. */
export function stepHref(id, { clientId, year = null, search = '' }) {
  const base = `/c/${encodeURIComponent(clientId)}`;
  if (id === 'eligibility' || id === 'evidence') {
    const params = new URLSearchParams();
    if (year != null) params.set('year', String(year));
    const query = params.toString();
    return `${base}/${id}${query ? `?${query}` : ''}`;
  }
  // A section keeps the rest of the page's query (year, method) and changes
  // only which question is showing. What-if's own scope belongs to What-if.
  const params = new URLSearchParams(search);
  if (id === DEFAULT_CLIENT_TAB) params.delete('ctab');
  else params.set('ctab', id);
  const query = params.toString();
  return `${base}${query ? `?${query}` : ''}`;
}

/**
 * The steps for the stepper. `current` is a step id (or null on a page the
 * stepper is shown on but that is not one of its steps).
 */
export function clientSteps({ clientId, year = null, search = '', current = null, clientScope = null }) {
  const reason = unavailableReason(clientScope);
  return STEPS.map((step) => {
    const blocked = reason && NEEDS_A_YEAR.has(step.id);
    return {
      id: step.id,
      label: step.label,
      title: step.hint,
      status: blocked ? 'disabled' : (step.id === current ? 'current' : 'upcoming'),
      reason: blocked ? reason : undefined,
      to: blocked ? undefined : stepHref(step.id, { clientId, year, search }),
    };
  });
}

/** The step a client route is showing: a section by `ctab`, a view by name. */
export function currentStep({ view = 'trend', ctab = DEFAULT_CLIENT_TAB }) {
  if (view === 'eligibility' || view === 'evidence') return view;
  return ctab;
}
