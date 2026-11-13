/*
 * Why: a pack is a handful of numbers and citations for the supported model, and a form is the safe way to author them: each
 * number is a labelled field with its own finding beside it, an empty field is stored as null (never a plausible guess) and the
 * citation fields are the ones the validator will not let stay empty. The advanced editor is the escape hatch for anything the
 * form does not cover; it parses before it applies and says why it cannot.
 * Never: fill a number the author did not type, copy values from another year, or call a value verified.
 */
import { useEffect, useState } from 'react';
import { coerce, fieldFinding, getIn, parseDocument, setIn } from '../../lib/programs.js';
import Button from '../ui/Button.jsx';
import { NotVerified } from './Badges.jsx';

function Field({ field, doc, onChange, finding, readOnly, id }) {
  const raw = getIn(doc, field.path);
  const value = raw == null ? '' : String(raw);
  const set = (event) => onChange(field, event.target.value);
  // The notes are descriptions, not part of the label, so the field's accessible name is just its label.
  const describedBy = [field.help ? `${id}-help` : null, field.number ? `${id}-nv` : null, finding ? `${id}-err` : null].filter(Boolean).join(' ') || undefined;
  const control = field.type === 'select'
    ? <select id={id} value={value} onChange={set} disabled={readOnly} aria-describedby={describedBy}><option value="">Choose</option>{field.options.map((o) => <option key={o} value={o}>{o}</option>)}</select>
    : <input id={id} type={field.number ? 'number' : 'text'} step="any" value={value} onChange={set} disabled={readOnly} aria-describedby={describedBy} aria-invalid={finding?.severity === 'error' ? 'true' : undefined} />;
  return (
    <div className={`prog-field${field.cite ? ' prog-field--wide' : ''}`}>
      <label htmlFor={id}>{field.label}</label>
      {control}
      {field.help ? <span id={`${id}-help`} className="prog-field-note">{field.help}</span> : null}
      {field.number ? <span id={`${id}-nv`} className="prog-field-note">Not verified: cite the source in the year pack.</span> : null}
      {finding ? <span id={`${id}-err`} className="prog-field-error" role="alert">{finding.message}</span> : null}
    </div>
  );
}
function Advanced({ doc, onApply, readOnly, label }) {
  const [text, setText] = useState(() => JSON.stringify(doc, null, 2));
  const [error, setError] = useState(null);
  useEffect(() => { setText(JSON.stringify(doc, null, 2)); setError(null); }, [doc]);
  const apply = () => {
    const parsed = parseDocument(text);
    if (!parsed.ok) { setError(parsed.error); return; }
    setError(null);
    onApply(parsed.value);
  };
  return (
    <details>
      <summary>Advanced: edit {label} as JSON</summary>
      <label className="prog-field" htmlFor={`${label}-json`}>
        <span>{label} JSON</span>
        <textarea id={`${label}-json`} className="prog-json" value={text} onChange={(e) => setText(e.target.value)} readOnly={readOnly} spellCheck="false" />
      </label>
      {error ? <p className="prog-field-error" role="alert">{error}</p> : null}
      <div className="prog-actions"><Button size="sm" onClick={apply} disabled={readOnly}>Apply JSON</Button></div>
    </details>
  );
}

/** `file` is the validator's file label for this document (`pack` or `year 2025`); `fields` is PACK_FIELDS or YEAR_FIELDS. */
export default function DocumentEditor({ doc, fields, file, label, validation, readOnly = false, onChange }) {
  const slug = file.replace(/\W+/g, '-');
  return (
    <div className="prog-stack">
      <p><NotVerified>Every value here is not verified</NotVerified></p>
      <div className="prog-fields">
        {fields.map((field) => (
          <Field
            key={field.path} id={`${slug}-${field.path.replace(/\W+/g, '-')}`} field={field} doc={doc} readOnly={readOnly}
            finding={fieldFinding(validation, file, field.path)}
            onChange={(f, raw) => onChange(setIn(doc, f.path, coerce(f, raw)))}
          />
        ))}
      </div>
      <Advanced doc={doc} label={label} readOnly={readOnly} onApply={onChange} />
    </div>
  );
}
