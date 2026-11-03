/*
 * Why: one status pill so a verdict looks the same on every screen. The glyph
 * exists so colour is never the only signal.
 * Never: take a colour from props, use brand blue for a verdict, or carry
 * meaning in colour alone when an icon is available.
 */
import './Pill.css';

const GLYPHS = { check: '✓', x: '✕', dot: '●' };
const VARIANTS = [
  'above-min',
  'below-min',
  'base-year',
  'partial',
  'neutral',
  'info',
  'category',
];

export default function Pill({
  variant = 'neutral',
  tone = 'soft',
  icon = null,
  children,
  className = '',
}) {
  const safeVariant = VARIANTS.includes(variant) ? variant : 'neutral';
  const safeTone = tone === 'outline' ? 'outline' : 'soft';
  const glyph = GLYPHS[icon];
  const classes = [
    'ui-pill',
    `ui-pill-${safeVariant}`,
    `ui-pill-${safeTone}`,
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <span className={classes}>
      {glyph && (
        <span className="ui-pill-icon" aria-hidden="true">
          {glyph}
        </span>
      )}
      {children}
    </span>
  );
}
