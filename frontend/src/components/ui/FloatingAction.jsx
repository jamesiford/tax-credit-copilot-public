/*
 * Why: a persistent assistant entry point that stays reachable on long pages.
 * The offset lives in a token (--floating-offset) precisely so it can cover
 * the page's primary action area nowhere: a page with a bottom action bar must
 * reserve space with FLOATING_CLEARANCE_CLASS on its scroll container.
 *
 * Never: sit over a primary action, appear in print, or carry a verdict.
 */
import './FloatingAction.css';

export const FLOATING_CLEARANCE_CLASS = 'ui-floating-clearance';

export default function FloatingAction({ icon, label, onClick, href, ...rest }) {
  const content = (
    <>
      {icon && (
        <span className="ui-floating__icon" aria-hidden="true">
          {icon}
        </span>
      )}
      <span className="ui-floating__label">{label}</span>
    </>
  );

  if (href) {
    return (
      <a className="ui-floating" href={href} onClick={onClick} {...rest}>
        {content}
      </a>
    );
  }
  return (
    <button type="button" className="ui-floating" onClick={onClick} {...rest}>
      {content}
    </button>
  );
}
