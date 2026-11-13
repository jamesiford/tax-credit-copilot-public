/*
 * Why: step 2 authors the base pack beside its own validation, so each finding is next to the field it is about. The structured
 * form covers the supported model; the advanced editor covers the rest. Saving is automatic and says when it last happened.
 * Never: let an edit through once the draft is under review (the review is of the documents it holds).
 */
import { PACK_FIELDS, saveBlocked } from '../../lib/programs.js';
import Callout from '../ui/Callout.jsx';
import Card from '../ui/Card.jsx';
import DocumentEditor from './DocumentEditor.jsx';
import ValidationPanel from './ValidationPanel.jsx';

export default function StepPack({ draft, docs, setDocs, stale }) {
  const blocked = saveBlocked(draft);
  const pack = docs?.pack || {};
  return (
    <div className="prog-grid-2">
      <Card title="Program pack" subtitle="The credit, its citation, its thresholds and the benefit. Citations are required for every number.">
        {blocked ? <Callout title="Read only"><p>{blocked}.</p></Callout> : null}
        <DocumentEditor
          doc={pack} fields={PACK_FIELDS} file="pack" label="base pack" validation={draft.validation} readOnly={Boolean(blocked)}
          onChange={(next) => setDocs(next, docs.years)}
        />
      </Card>
      <ValidationPanel validation={draft.validation} files={['pack', 'draft']} stale={stale} />
    </div>
  );
}
