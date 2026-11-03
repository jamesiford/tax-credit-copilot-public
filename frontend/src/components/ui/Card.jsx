/*
 * Why: one container for a block of content so surface, border and shadow are
 * decided once. The section is labelled by its title so it is a landmark-like
 * region a screen reader can name.
 * `tone` is a surface ('neutral' | 'subtle') or a verdict (a --state-* family:
 * the border then encodes the reading). `flush` removes the body padding for a
 * dense data grid, which is the point of its page.
 * Never: render an empty header, hard-code a colour, or lay out its children
 * (the caller owns the body).
 */
import { useId } from 'react';
import './Card.css';

//: A verdict card's border carries the reading. These are the --state-* families
//: and nothing else, so a border is never the selection blue.
const VERDICTS = ['above-min', 'below-min', 'partial', 'base-year'];

export default function Card({
  title,
  subtitle,
  actions,
  tabs,
  footer,
  tone = 'neutral',
  flush = false,
  as: Element = 'section',
  label,
  children,
  className = '',
}) {
  const titleId = useId();
  const hasHeader = Boolean(title || subtitle || actions);
  const verdict = VERDICTS.includes(tone) ? tone : null;
  const classes = [
    'ui-card',
    tone === 'subtle' ? 'ui-card-subtle' : 'ui-card-neutral',
    verdict ? `ui-card-verdict ui-card-verdict-${verdict}` : '',
    flush ? 'ui-card-flush' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <Element
      className={classes}
      aria-labelledby={title ? titleId : undefined}
      aria-label={!title && label ? label : undefined}
    >
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
