import './Button.css';

/**
 * The one button. Five variants, two sizes, nothing else.
 *
 * It exists so a "primary action" is one thing: the gradient fill is the ONLY
 * place it appears, which is what stops every screen growing its own blue
 * button. `danger` is drawn from the below-minimum state family rather than a
 * free red, so a destructive action and a failing reading cannot disagree.
 *
 * Never: put a verdict on a button (that is a Pill), or hand-roll
 * `<button class="btn ...">` in a view. A `href` renders a link with the same
 * look, so navigation and action stay visually one family while keeping their
 * own semantics.
 */
const VARIANTS = ['primary', 'secondary', 'ghost', 'link', 'danger'];

export default function Button({
  variant = 'secondary',
  size = 'md',
  icon = null,
  loading = false,
  disabled = false,
  href,
  type = 'button',
  className = '',
  children,
  ...rest
}) {
  const kind = VARIANTS.includes(variant) ? variant : 'secondary';
  const cls = ['ui-btn', `ui-btn-${kind}`, size === 'sm' ? 'ui-btn-sm' : '', className].filter(Boolean).join(' ');
  const inert = disabled || loading;
  const content = (
    <>
      {loading ? <span className="ui-btn-spinner" aria-hidden="true" /> : icon ? <span className="ui-btn-icon" aria-hidden="true">{icon}</span> : null}
      {children}
    </>
  );

  if (href && !inert) {
    return <a className={cls} href={href} {...rest}>{content}</a>;
  }
  return (
    <button
      type={type}
      className={cls}
      disabled={inert}
      aria-busy={loading || undefined}
      {...rest}
    >
      {content}
    </button>
  );
}
