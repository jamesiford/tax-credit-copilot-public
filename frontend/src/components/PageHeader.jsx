/**
 * Eyebrow, title, subtitle, optional action. Every page, one spacing scale.
 *
 * There were six header treatments, including a dark navy banner on the
 * employee walk that was left over from when it was a modal.
 */
export default function PageHeader({ eyebrow, title, sub, icon, actions }) {
  return (
    <div className="tcc-header">
      <div>
        {eyebrow ? <div className="tcc-eyebrow">{eyebrow}</div> : null}
        <h1 className={`page-title${icon ? ' tcc-title-with-icon' : ''}`}>
          {icon}
          {icon ? <span>{title}</span> : title}
        </h1>
        {sub ? <p className="page-sub">{sub}</p> : null}
      </div>
      {actions ? <div className="tcc-header-actions">{actions}</div> : null}
    </div>
  );
}
