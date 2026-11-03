/*
 * Why: a screen with nothing on it must say why, and what to do, or it reads as
 * broken. This lays out whatever the caller says; the wording is theirs.
 * Never: supply its own explanation, say "No data" on its own, or imply that
 * "not yet looked at" and "looked and found nothing" are the same.
 */
import './EmptyState.css';

export default function EmptyState({
  title,
  children,
  action,
  icon,
  className = '',
}) {
  return (
    <div
      className={['ui-empty', className].filter(Boolean).join(' ')}
      role="status"
    >
      {icon && (
        <div className="ui-empty-icon" aria-hidden="true">
          {icon}
        </div>
      )}
      {title && <p className="ui-empty-title">{title}</p>}
      {children && <div className="ui-empty-body">{children}</div>}
      {action && <div className="ui-empty-action">{action}</div>}
    </div>
  );
}
