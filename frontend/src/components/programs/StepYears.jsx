/*
 * Why: step 3 authors one year pack at a time. A tax year is its own complete pack, never inherited from another (ADR-005), so
 * "add a year" starts from an empty flagged skeleton for the program's identity only and copies no value from any other year.
 * Never: copy a value across years, or offer a year that already exists.
 */
import { useState } from 'react';
import { YEAR_FIELDS, saveBlocked, yearSkeleton } from '../../lib/programs.js';
import Button from '../ui/Button.jsx';
import Callout from '../ui/Callout.jsx';
import Card from '../ui/Card.jsx';
import DocumentEditor from './DocumentEditor.jsx';
import ValidationPanel from './ValidationPanel.jsx';

export default function StepYears({ draft, docs, setDocs, stale }) {
  const years = Object.keys(docs?.years || {}).sort();
  const [selected, setSelected] = useState(years[years.length - 1] || null);
  const [newYear, setNewYear] = useState('');
  const blocked = saveBlocked(draft);
  const current = selected && docs.years[selected] ? selected : years[years.length - 1] || null;
  const validYear = Number.isInteger(Number(newYear)) && Number(newYear) >= 1990 && Number(newYear) < 2200;
  const exists = years.includes(String(newYear).trim());
  const add = () => {
    const key = String(Number(newYear));
    setDocs(docs.pack, { ...docs.years, [key]: yearSkeleton(docs.pack, key) });
    setSelected(key); setNewYear('');
  };
  const remove = (key) => {
    const { [key]: _gone, ...rest } = docs.years;
    setDocs(docs.pack, rest);
    setSelected(null);
  };
  return (
    <div className="prog-grid-2">
      <Card title="Year packs" subtitle="Each tax year is complete on its own: nothing is inherited from another year.">
        {blocked ? <Callout title="Read only"><p>{blocked}.</p></Callout> : null}
        <div className="prog-years" role="group" aria-label="Authored years">
          {years.map((y) => (
            <Button key={y} size="sm" variant={y === current ? 'primary' : 'secondary'} aria-pressed={y === current} onClick={() => setSelected(y)}>{y}</Button>
          ))}
          {!years.length ? <p className="small muted">No year yet. Without one the program is described, not calculable.</p> : null}
        </div>
        {!blocked ? (
          <div className="prog-actions">
            <label className="prog-field"><span>Add a tax year</span>
              <input value={newYear} onChange={(e) => setNewYear(e.target.value)} inputMode="numeric" placeholder="2026" /></label>
            <Button onClick={add} disabled={!validYear || exists}>Add {newYear || 'year'}</Button>
            {exists ? <span className="prog-field-note" role="status">That year is already in the draft.</span> : null}
            {current ? <Button variant="ghost" size="sm" onClick={() => remove(current)}>Remove {current}</Button> : null}
          </div>
        ) : null}
        {current ? (
          <DocumentEditor
            doc={docs.years[current]} fields={YEAR_FIELDS} file={`year ${current}`} label={`${current} year pack`} validation={draft.validation}
            readOnly={Boolean(blocked)} onChange={(next) => setDocs(docs.pack, { ...docs.years, [current]: next })}
          />
        ) : null}
      </Card>
      <ValidationPanel validation={draft.validation} files={current ? [`year ${current}`] : ['draft']} stale={stale} title={current ? `Validation: ${current}` : 'Validation'} />
    </div>
  );
}
