import MetaLine from './ui/MetaLine.jsx';

/**
 * Eyebrow, title, subtitle, optional action. Every page, one spacing scale.
 *
 * There were six header treatments, including a dark navy banner on the
 * employee walk that was left over from when it was a modal. `meta` is the
 * `Label: value · Label: value` line under the title (client, tax year, method,
 * run); it is a slot here so no page grows its own.
 */
export default function PageHeader({ eyebrow, title, sub, meta, icon, actions }) {
  return (
    <div className="tcc-header">
      <div>
        {eyebrow ? <div className="tcc-eyebrow">{eyebrow}</div> : null}
        <h1 className={`page-title${icon ? ' tcc-title-with-icon' : ''}`}>
          {icon}
          {icon ? <span>{title}</span> : title}
        </h1>
        {sub ? <p className="page-sub">{sub}</p> : null}
        {meta?.length ? <MetaLine items={meta} className="u-mt-2" /> : null}
      </div>
      {actions ? <div className="tcc-header-actions">{actions}</div> : null}
    </div>
  );
}
