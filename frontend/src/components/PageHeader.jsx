import { ArrowLeft } from 'lucide-react';
import MetaLine from './ui/MetaLine.jsx';

/**
 * Eyebrow, title, subtitle, optional action. Every page, one spacing scale.
 *
 * `back` is a link to the previous drill level (`{ label, onClick }`).
 * `compact` lays the back link, title and meta on one row, for a page whose
 * rows are the point and whose fold is measured. It is the same header, not a
 * second one.
 *
 * There were six header treatments, including a dark navy banner on the
 * employee walk that was left over from when it was a modal. `meta` is the
 * `Label: value · Label: value` line under the title (client, tax year, method,
 * run); it is a slot here so no page grows its own.
 */
export default function PageHeader({
  eyebrow, title, sub, meta, icon, actions, back, compact = false,
}) {
  return (
    <div className={`tcc-header${compact ? ' tcc-header-compact' : ''}`}>
      <div>
        {back ? (
          <button type="button" className="tcc-review-back" onClick={back.onClick}>
            <ArrowLeft size={14} aria-hidden="true" /> {back.label}
          </button>
        ) : null}
        {eyebrow ? <div className="tcc-eyebrow">{eyebrow}</div> : null}
        <h1 className={`page-title${icon ? ' tcc-title-with-icon' : ''}`}>
          {icon}
          {icon ? <span>{title}</span> : title}
        </h1>
        {sub ? <p className="page-sub">{sub}</p> : null}
        {meta?.length ? <MetaLine items={meta} className={compact ? undefined : 'u-mt-2'} /> : null}
      </div>
      {actions ? <div className="tcc-header-actions">{actions}</div> : null}
    </div>
  );
}
