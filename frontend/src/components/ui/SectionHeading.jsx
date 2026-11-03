/*
 * Why: every list and grid is introduced the same way, "Title (count)", so the
 * size of what follows is stated before it is read, and the heading level is
 * chosen by the page outline rather than by how big it should look.
 * Never: skip the count's parentheses, pick a level for its size, or render a
 * count that was not supplied.
 */
import './SectionHeading.css';

const LEVELS = { 2: 'h2', 3: 'h3', 4: 'h4' };

export default function SectionHeading({
  children,
  count,
  level = 2,
  className = '',
}) {
  const Tag = LEVELS[level] || 'h2';
  const hasCount = typeof count === 'number' && Number.isFinite(count);

  return (
    <Tag className={['ui-section-heading', className].filter(Boolean).join(' ')}>
      {children}
      {hasCount && <span className="ui-section-heading-count"> ({count})</span>}
    </Tag>
  );
}
