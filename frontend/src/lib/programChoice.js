/**
 * Which program a run or an assessment is for, when a state holds more than one. [F04c.8]
 *
 * A state used to resolve to exactly one program, so no control had to say which. Now a state can hold several, and a
 * control that does not say prices the first with a warning, which is the thing this work removes. Everything here is
 * derived from the scope options (`/api/scope`) and never typed in: a state with ONE calculable program yields no choice,
 * so a single-program state renders and calls exactly as before.
 */

import { ALL_PROGRAMS } from './scopeDimension.js';

/** The one program a scope names, or null at all-programs scope (which names none). */
export const scopeProgram = (scope) => (scope?.programCode && scope.programCode !== ALL_PROGRAMS ? scope.programCode : null);

/** Programs the engine can price: statute authored for at least one year, and a state to take payroll rows from. */
export function calculablePrograms(scopeOptions) {
  return (scopeOptions?.programs || []).filter(
    (p) => (p.authored_years || []).length && p.jurisdiction?.level !== 'federal' && p.jurisdiction?.code,
  );
}

/** The calculable programs of one state, in the order the registry lists them (the first is the state's default). */
export function programsInState(scopeOptions, state) {
  const wanted = String(state || '').toUpperCase();
  return calculablePrograms(scopeOptions).filter((p) => String(p.jurisdiction.code).toUpperCase() === wanted);
}

/** Whether a control must show and pass a program for this state. */
export const hasSeveralPrograms = (scopeOptions, state) => programsInState(scopeOptions, state).length > 1;

/**
 * The program a control passes. The scope's own program wins when it belongs to the state; otherwise the state's first
 * program is offered (never sent silently: the picker shows it). `null` for a state with a single program, which sends nothing.
 */
export function chosenProgram(scopeOptions, state, scopeProgramCode, picked) {
  const programs = programsInState(scopeOptions, state);
  if (programs.length < 2) return null;
  const known = (code) => programs.some((p) => p.program_code === code);
  if (picked && known(picked)) return picked;
  if (scopeProgramCode && known(scopeProgramCode)) return scopeProgramCode;
  return programs[0].program_code;
}

export const programName = (p) => (p.name && p.name !== p.program_code ? `${p.name} (${p.program_code})` : p.program_code);
