import { programName, programsInState } from '../lib/programChoice.js';

/**
 * Picks the program for a run or an assessment, only where the state holds several. [F04c.8]
 *
 * Renders nothing for a single-program state, so those screens look exactly as before. `allowAll` adds "Every program of
 * the state" for an assessment, which sweeps them all; a calculation is always for one program, so it never offers it.
 */
export default function ProgramPicker({ scopeOptions, state, value, onChange, allowAll = false, disabled = false }) {
  const programs = programsInState(scopeOptions, state);
  if (programs.length < 2) return null;
  return (
    <label className="tcc-program-picker small">
      <span className="muted">Program </span>
      <select value={value ?? ''} disabled={disabled} onChange={(e) => onChange(e.target.value)} aria-label="Program">
        {allowAll ? <option value="">Every program of {String(state).toUpperCase()}</option> : null}
        {programs.map((p) => <option key={p.program_code} value={p.program_code}>{programName(p)}</option>)}
      </select>
    </label>
  );
}
