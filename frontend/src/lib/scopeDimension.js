/**
 * The scope DIMENSION: persistent `client x program x year`.
 *
 * Distinct from `lib/scope.js`, which is the older Georgia-only display filter
 * used by the legacy portal. This module is the axis system the data-driven
 * shell moves through.
 *
 * Scope is not a view and not a filter panel. Every calculating screen renders
 * at some point in that space, and the operator moves through it rather than
 * navigating somewhere else to change client. That is why it lives in the shell
 * and survives navigation.
 *
 * The reducer is here rather than inside the component because the interesting
 * behaviour is not rendering — it is what a selection *invalidates*. Choosing a
 * client whose payroll does not cover the selected year has to resolve to
 * something honest rather than to an empty screen, and that rule deserves a
 * test.
 */

export const PORTFOLIO = 'portfolio';
export const ALL_PROGRAMS = 'all';

const STORAGE_KEY = 'tcc.scope.v1';

export const initialScope = {
  clientId: PORTFOLIO,       // PORTFOLIO or an account id
  programCode: ALL_PROGRAMS, // ALL_PROGRAMS or a program code
  year: null,                // a single tax year, or null until options load
  windowMode: false,         // false = single year, true = retroactive window
};

/**
 * Jurisdiction is DERIVED from the programme, never selected.
 *
 * A programme belongs to exactly one jurisdiction, so offering both axes lets
 * an operator build a contradiction ("Georgia" + "Federal WOTC") that has no
 * meaning. At all-programmes scope the answer is every jurisdiction in play,
 * which is a fact about the selection rather than another choice.
 */
export function derivedJurisdictions(scope, options) {
  const programs = options?.programs || [];
  if (scope.programCode !== ALL_PROGRAMS) {
    const one = programs.find((p) => p.program_code === scope.programCode);
    return one ? [one.jurisdiction] : [];
  }
  const seen = new Map();
  programs.forEach((p) => {
    if (p.jurisdiction?.code) seen.set(p.jurisdiction.code, p.jurisdiction);
  });
  return [...seen.values()].sort((a, b) => a.code.localeCompare(b.code));
}

/**
 * The single programme a selection can actually be priced under, if there is
 * exactly one.
 *
 * `ALL_PROGRAMS` is honest at the book, where the question spans every
 * jurisdiction. It is a dead end everywhere else: Progress and What-if both
 * need ONE statute to measure against, and refuse to render without it. While
 * the shell carried a scope bar an operator could resolve that themselves.
 * Now that it does not, "all" became a state with no exit — both views showed
 * "Select a single program" with nothing on screen able to select one.
 *
 * Nine programmes are codified and eight report `calculable: false`, so in
 * practice there is nothing to choose. Resolving is therefore not a guess: it
 * is naming the only answer. When two or more are calculable the ambiguity is
 * real, and picking one would be inventing an answer — so it stays `all` and
 * the views keep asking.
 */
function onlyCalculableProgram(programs) {
  const priceable = (programs || []).filter((p) => p.calculable);
  return priceable.length === 1 ? priceable[0].program_code : null;
}

/**
 * The years a selection can be calculated for.
 *
 * Intersects what the programme's statute covers with what the client's payroll
 * actually holds. Those two sets differ routinely — payroll runs past the last
 * published wage table — and the gap is reported, not hidden.
 */
export function calculableYears(options, clientScope, programCode) {
  const programs = options?.programs || [];
  const relevant = programCode === ALL_PROGRAMS
    ? programs
    : programs.filter((p) => p.program_code === programCode);

  const statuteYears = new Set(relevant.flatMap((p) => p.authored_years || []));
  if (!clientScope) return [...statuteYears].sort((a, b) => a - b);

  const payroll = new Set(clientScope.payroll_years || []);
  return [...statuteYears].filter((y) => payroll.has(y)).sort((a, b) => a - b);
}

/**
 * Years whose statute is a PLACEHOLDER — authored so the year can be read, but
 * not published (TY2026's Georgia wage floor is carried forward from TY2025).
 * Every view of such a year says so; a floor nobody published must not look
 * like one somebody did.
 */
export function placeholderYears(options, programCode) {
  const programs = options?.programs || [];
  const relevant = programCode === ALL_PROGRAMS
    ? programs
    : programs.filter((p) => p.program_code === programCode);
  return [...new Set(relevant.flatMap((p) => p.placeholder_years || []))].sort((a, b) => a - b);
}

/** The retroactive window ending at `year`: a base year plus five. */
export function windowFor(year, available, windowYears = 6) {
  if (year == null) return [];
  return available.filter((y) => y <= year && y > year - windowYears).sort((a, b) => a - b);
}

/**
 * Resolve a scope against the options actually available.
 *
 * Returns `{ scope, notices, availableYears, window }`. A notice records where a
 * selection could not be honoured and what happened instead — switching client
 * must not silently move the year underneath the operator, because the year
 * decides which statute applies and a figure computed under the wrong one is
 * worse than no figure.
 */
export function reconcileScope(scope, options, clientScope) {
  const notices = [];
  const next = { ...scope };

  const programs = options?.programs || [];
  if (next.programCode !== ALL_PROGRAMS) {
    const chosen = programs.find((p) => p.program_code === next.programCode);
    if (!chosen) {
      notices.push({ axis: 'program', message: `${next.programCode} is not available; showing all programs.` });
      next.programCode = ALL_PROGRAMS;
    } else if (!chosen.calculable) {
      notices.push({ axis: 'program', message: chosen.not_calculable_reason || `${chosen.name} cannot be calculated.` });
    }
  }

  // Resolve "all" down to the one priceable programme when there is only one.
  // This runs AFTER the fallback above, so an unknown programme lands on the
  // one we can actually price rather than on a scope no view can render. The
  // notice still fires, because the operator asked for something we did not
  // honour and that has to be said.
  if (next.programCode === ALL_PROGRAMS) {
    const only = onlyCalculableProgram(programs);
    if (only) next.programCode = only;
  }

  const available = calculableYears(options, clientScope, next.programCode);
  if (!available.length) {
    if (next.year != null) {
      notices.push({ axis: 'year', message: 'No tax year can be calculated for this selection.' });
    }
    return { scope: { ...next, year: null }, notices, availableYears: [], window: [] };
  }

  if (next.year == null) {
    // Open on the most recent COMPLETE year, not simply the most recent one.
    // A partial year prices at a low average headcount and renders as "$0" —
    // which reads as "this client earned nothing" rather than "we hold eight
    // months of this year".
    const preferred = clientScope?.default_year;
    next.year = available.includes(preferred)
      ? preferred
      : available[available.length - 1];
  } else if (!available.includes(next.year)) {
    // Same preference as the opening year. A cold load picks a year from the
    // statute before the client's payroll arrives, so this branch is how most
    // client pages actually land — and falling to the newest year here put
    // Candle Bottle on TY2024, two months of payroll no run has priced.
    const preferred = clientScope?.default_year;
    const fallback = available.includes(preferred) ? preferred : available[available.length - 1];
    notices.push({
      axis: 'year',
      message: `TY${next.year} is not available for this selection \u2014 moved to TY${fallback}.`,
    });
    next.year = fallback;
  }

  const windowYears = options?.years?.window_years || 6;
  return {
    scope: next,
    notices,
    availableYears: available,
    window: next.windowMode ? windowFor(next.year, available, windowYears) : [next.year],
  };
}

/** Years we hold payroll for but cannot price. Surfaced, never dropped. */
export function unpriceableYears(clientScope) {
  return [...(clientScope?.payroll_without_statute || [])].sort((a, b) => a - b);
}

/** A short human label, used in the shell and in run provenance. */
export function scopeLabel(scope, options, clientScope) {
  const client = scope.clientId === PORTFOLIO
    ? 'All clients'
    : (options?.clients || []).find((c) => String(c.account_id) === String(scope.clientId))?.name
      || `Account ${scope.clientId}`;

  const program = scope.programCode === ALL_PROGRAMS
    ? 'All programs'
    : (options?.programs || []).find((p) => p.program_code === scope.programCode)?.name
      || scope.programCode;

  const years = reconcileScope(scope, options, clientScope).window;
  const when = years.length > 1
    ? `TY${years[0]}\u2013${years[years.length - 1]}`
    : years[0] != null ? `TY${years[0]}` : 'no priceable year';

  return `${client} \u00b7 ${program} \u00b7 ${when}`;
}

export function loadStoredScope() {
  try {
    const raw = window.localStorage?.getItem(STORAGE_KEY);
    if (!raw) return { ...initialScope };
    return { ...initialScope, ...JSON.parse(raw) };
  } catch {
    return { ...initialScope };
  }
}

export function storeScope(scope) {
  try {
    window.localStorage?.setItem(STORAGE_KEY, JSON.stringify(scope));
  } catch { /* storage unavailable (private mode); scope stays in memory */ }
}
