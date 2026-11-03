import { useRef } from 'react';
import './Tabs.css';

/**
 * The one tab implementation.
 *
 * `SectionTabs`, `GridTabs` and `MethodTabs` were three hand-rolled rows of
 * buttons with three keyboard behaviours (one had none). They are wrappers over
 * this now, so "which of these is a tab" is not something a reader works out.
 *
 * Selection is the brand blue and nothing else: a tab carries a CHOICE, never a
 * verdict, which is why it never reads a --state-* colour. The count is part of
 * the label because "Who to call" does not say whether to click and
 * "Who to call (4)" does.
 *
 * Roving tabindex: one tab stop for the whole list, arrows move within it. Never
 * make every tab tabbable, and never render a tab that is not in a tablist.
 */
export default function Tabs({
  tabs,
  active,
  onChange,
  label = 'Tabs',
  idPrefix = 'tabs',
  variant = 'underline',
  controls = true,
  className = '',
}) {
  const refs = useRef({});
  const enabled = tabs.filter((tab) => !tab.disabled);

  const move = (current, delta) => {
    const index = enabled.findIndex((tab) => tab.id === current);
    const next = enabled[(index + delta + enabled.length) % enabled.length];
    if (!next) return;
    refs.current[next.id]?.focus();
    onChange(next.id);
  };

  const onKeyDown = (event, id) => {
    const keys = { ArrowRight: () => move(id, 1), ArrowLeft: () => move(id, -1) };
    if (event.key === 'Home' && enabled.length) {
      event.preventDefault();
      refs.current[enabled[0].id]?.focus();
      onChange(enabled[0].id);
    } else if (event.key === 'End' && enabled.length) {
      event.preventDefault();
      const last = enabled[enabled.length - 1];
      refs.current[last.id]?.focus();
      onChange(last.id);
    } else if (keys[event.key]) {
      event.preventDefault();
      keys[event.key]();
    }
  };

  // With nothing active, the first enabled tab takes the single tab stop.
  const stop = enabled.some((tab) => tab.id === active) ? active : enabled[0]?.id;

  return (
    <div
      className={`ui-tabs ui-tabs-${variant}${className ? ` ${className}` : ''}`}
      role="tablist"
      aria-label={label}
    >
      {tabs.map((tab) => {
        const selected = tab.id === active;
        return (
          <button
            key={tab.id}
            ref={(node) => { refs.current[tab.id] = node; }}
            type="button"
            role="tab"
            className="ui-tab"
            id={`${idPrefix}-tab-${tab.id}`}
            aria-selected={selected}
            aria-controls={controls ? `${idPrefix}-panel-${tab.id}` : undefined}
            tabIndex={tab.id === stop ? 0 : -1}
            disabled={tab.disabled}
            title={tab.hint}
            onClick={() => onChange(tab.id)}
            onKeyDown={(event) => onKeyDown(event, tab.id)}
          >
            {tab.label}
            {tab.count == null ? null : <span className="ui-tab-count">{tab.count}</span>}
          </button>
        );
      })}
    </div>
  );
}
