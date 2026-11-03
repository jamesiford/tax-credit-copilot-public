/*
 * Why: a task is one destination, so the whole card is one link — a single
 * tab stop and one hit target, not a card with a link buried inside it.
 *
 * Never: nest interactive elements, swallow modifier-clicks (they must still
 * open a new tab), or use a verdict colour for the category chip.
 */
import { useId } from 'react';
import './TaskCard.css';

const isPlainLeftClick = (e) =>
  e.button === 0 && !e.ctrlKey && !e.metaKey && !e.shiftKey && !e.altKey;

export default function TaskCard({ href, title, description, category, icon, onClick }) {
  const id = useId();
  const titleId = `${id}-title`;
  const descId = `${id}-desc`;

  const handleClick = onClick
    ? (event) => {
        if (!isPlainLeftClick(event)) return;
        event.preventDefault();
        onClick(event);
      }
    : undefined;

  return (
    <a
      className="ui-task-card"
      href={href}
      onClick={handleClick}
      aria-labelledby={titleId}
      aria-describedby={description ? descId : undefined}
    >
      {icon && (
        <span className="ui-task-icon" aria-hidden="true">
          {icon}
        </span>
      )}
      <span className="ui-task-body">
        <span className="ui-task-heading">
          <span className="ui-task-title" id={titleId}>
            {title}
          </span>
          {category && <span className="ui-task-category">{category}</span>}
        </span>
        {description && (
          <span className="ui-task-description" id={descId} title={description}>
            {description}
          </span>
        )}
      </span>
      <span className="ui-task-chevron" aria-hidden="true">
        ›
      </span>
    </a>
  );
}
