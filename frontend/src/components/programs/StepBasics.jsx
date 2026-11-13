/*
 * Why: step 1 names the program and shows what already sits in that state, because programs in one state are independent: each
 * is calculated and assessed on its own program code. A federal program has no state and is not runnable yet, so it is shown that
 * way and cannot be started. Creating the draft scaffolds empty, flagged packs; nothing is calculable and nothing is verified.
 * Never: offer to start a federal draft, or pre-fill a statutory value.
 */
import { useState } from 'react';
import Button from '../ui/Button.jsx';
import Callout from '../ui/Callout.jsx';
import Card from '../ui/Card.jsx';
import { programsInStateOf } from '../../lib/programs.js';
import { LifecycleBadge } from './Badges.jsx';

const CODE = /^[A-Z][A-Z0-9_]{2,63}$/;

function Neighbours({ rows, state }) {
  const here = programsInStateOf(rows, state);
  if (!state) return null;
  if (!here.length) return <p className="small muted">No program is registered for {state.toUpperCase()} yet.</p>;
  return (
    <Callout title={`Already registered for ${state.toUpperCase()}`}>
      <p>Programs in one state are independent: each is calculated and assessed on its own program code, so the new one sits beside these without changing them.</p>
      <ul>{here.map((p) => <li key={p.code}>{p.name} (<code>{p.code}</code>) <LifecycleBadge lifecycle={p.lifecycle} /></li>)}</ul>
    </Callout>
  );
}

function Summary({ draft }) {
  return (
    <Card title="Basics" subtitle="Fixed once the draft exists; start another draft to change them">
      <dl className="small">
        <dt>Program code</dt><dd><code>{draft.proposed_code}</code></dd>
        <dt>Name</dt><dd>{draft.name}</dd>
        <dt>State</dt><dd>{draft.state}</dd>
        <dt>Pack file</dt><dd><code>{draft.pack_file}</code></dd>
      </dl>
    </Card>
  );
}

export default function StepBasics({ draft, catalog, onCreate }) {
  const [form, setForm] = useState({ code: '', name: '', state: '', years: '', federal: false });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  if (draft) return <Summary draft={draft} />;
  const set = (key) => (event) => setForm((f) => ({ ...f, [key]: event.target.type === 'checkbox' ? event.target.checked : event.target.value }));
  const years = form.years.split(/[\s,]+/).filter(Boolean).map(Number);
  const problem = form.federal ? 'A federal program has no state, and a run prices a state\u2019s payroll rows: federal programs are not runnable yet.'
    : !CODE.test(form.code.trim().toUpperCase()) ? 'The code is upper case letters, digits and underscores, starting with a letter.'
      : !/^[A-Za-z]{2}$/.test(form.state.trim()) ? 'The state is its two-letter code.'
        : !form.name.trim() ? 'Name the credit.' : years.some((y) => !Number.isInteger(y) || y < 1990) ? 'Years are four-digit tax years.' : null;
  const submit = async (event) => {
    event.preventDefault();
    setBusy(true); setError(null);
    try { await onCreate({ code: form.code.trim().toUpperCase(), name: form.name.trim(), state: form.state.trim().toUpperCase(), years }); }
    catch (reason) { setError(reason); setBusy(false); }
  };
  return (
    <form className="prog-stack" onSubmit={submit} aria-label="Program basics">
      <div className="prog-fields">
        <label className="prog-field"><span>Program code</span>
          <input value={form.code} onChange={set('code')} placeholder="XX_EXAMPLE_JTC" disabled={form.federal} /></label>
        <label className="prog-field"><span>Credit name</span><input value={form.name} onChange={set('name')} disabled={form.federal} /></label>
        <label className="prog-field"><span>State (two letters)</span><input value={form.state} onChange={set('state')} maxLength={2} disabled={form.federal} /></label>
        <label className="prog-field"><span>Tax years to start with (optional)</span><input value={form.years} onChange={set('years')} placeholder="2025, 2026" disabled={form.federal} /></label>
        <label className="prog-field prog-field--wide"><span>
          <input type="checkbox" checked={form.federal} onChange={set('federal')} /> This is a federal program (no state)</span></label>
      </div>
      <Neighbours rows={catalog} state={form.federal ? '' : form.state} />
      {form.federal ? <Callout tone="partial" title="Federal programs are not runnable yet"><p>{problem}</p></Callout> : null}
      {error ? <Callout tone="partial" title="The draft was not created"><p>{error.reason || error.message}</p></Callout> : null}
      <div className="prog-actions">
        <Button variant="primary" type="submit" disabled={Boolean(problem) || busy} loading={busy}>Create the draft</Button>
        {problem && !form.federal ? <span className="prog-field-note" role="status">{problem}</span> : null}
      </div>
      <p className="prog-field-note">The draft starts from an empty, flagged template: no statutory value is filled in and nothing is verified.</p>
    </form>
  );
}
