/*
 * Why: one container for a block of content so surface, border and shadow are
 * decided once. The section is labelled by its title so it is a landmark-like
 * region a screen reader can name.
 * Never: render an empty header, hard-code a colour, or lay out its children
 * (the caller owns the body).
 */
import { useId } from 'react';
import './Card.css';

export default function Card({
  title,
  subtitle,
  actions,
  tabs,
  footer,
  tone = 'neutral',
  as: Element = 'section',
  children,
  className = '',
}) {
  const titleId = useId();
  const hasHeader = Boolean(title || subtitle || actions);
  const classes = [
    'ui-card',
    tone === 'subtle' ? 'ui-card-subtle' : 'ui-card-neutral',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <Element className={classes} aria-labelledby={title ? titleId : undefined}>
      {hasHeader && (
        <header className="ui-card-header">
          <div className="ui-card-heading">
            {title && (
              <h3 className="ui-card-title" id={titleId}>
                {title}
              </h3>
            )}
            {subtitle && <p className="ui-card-subtitle">{subtitle}</p>}
          </div>
          {actions && <div className="ui-card-actions">{actions}</div>}
        </header>
      )}
      {tabs && <div className="ui-card-tabs">{tabs}</div>}
      <div className="ui-card-body">{children}</div>
      {footer && <footer className="ui-card-footer">{footer}</footer>}
    </Element>
  );
}
