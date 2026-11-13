/*
 * Why: validation shows beside the document being edited, grouped by file, each finding addressed to a field (its path), errors
 * first. A pass reads "valid, not verified": the unverified flags are listed as information, never hidden.
 * Never: say a pack is verified or correct, or drop findings silently (a capped list says how many it hides).
 */
import { AlertTriangle, CheckCircle2, Info } from 'lucide-react';
import { fileLabel, validationSummary } from '../../lib/programs.js';
import Card from '../ui/Card.jsx';

const ICON = { error: AlertTriangle, warning: AlertTriangle, info: Info };
const SEVERITY = { error: 'Error', warning: 'Warning', info: 'Information' };

function Finding({ finding }) {
  const Icon = ICON[finding.severity] || Info;
  return (
    <li className="prog-finding" data-severity={finding.severity}>
      <span aria-hidden="true"><Icon size={14} /></span>
      <span>
        <span className="ui-visually-hidden">{SEVERITY[finding.severity]}: </span>
        {finding.path ? <code>{finding.path}</code> : null}{finding.path ? ' ' : ''}{finding.message}
      </span>
    </li>
  );
}

/** `files` limits the panel to the documents being edited on this step (for example `['pack', 'draft']`). */
export default function ValidationPanel({ validation, files = null, title = 'Validation', stale = false }) {
  const findings = (validation?.findings || []).filter((f) => !files || files.includes(f.file));
  const groups = [...new Set(findings.map((f) => f.file))];
  const shown = findings.filter((f) => f.severity !== 'info');
  const infoCount = findings.length - shown.length;
  return (
    <Card title={title} subtitle={validationSummary(validation)} tone={validation && !validation.valid ? 'partial' : 'neutral'}>
      {stale ? <p className="prog-field-note" role="status">Edited since this was validated: validate again before requesting review.</p> : null}
      {validation && !findings.length ? (
        <p><CheckCircle2 size={14} aria-hidden="true" /> No findings for this document. Valid is not verified.</p>
      ) : null}
      {groups.map((file) => (
        <section key={file} aria-label={`${fileLabel(file)} findings`}>
          <h4>{fileLabel(file)}</h4>
          <ul className="prog-findings">
            {shown.filter((f) => f.file === file).map((f, i) => <Finding key={`${f.code}-${f.path}-${i}`} finding={f} />)}
          </ul>
        </section>
      ))}
      {infoCount ? <p className="prog-field-note">{infoCount} unverified flag{infoCount === 1 ? '' : 's'} (_prototype_verify): each value stays not verified until a person checks it.</p> : null}
      {validation?.truncated ? <p className="prog-field-note">The list is capped; fix the errors shown, then validate again to see the rest.</p> : null}
      {!validation ? <p className="prog-field-note">Validate the draft to see field-level errors and warnings.</p> : null}
    </Card>
  );
}
