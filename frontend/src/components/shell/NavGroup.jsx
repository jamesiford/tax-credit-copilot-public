import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import './shell.css';

/**
 * One group of the top navigation, as a menu button.
 *
 * It follows the WAI-ARIA menu-button pattern because a group is a set of
 * ACTIONS that take you somewhere, not a page's own content:
 *   - Enter, Space or ArrowDown on the trigger opens it on the first item,
 *     ArrowUp opens it on the last;
 *   - arrows, Home and End move within it, and wrap;
 *   - Escape closes it and returns focus to the trigger; Tab closes it;
 *   - a click outside closes it.
 *
 * An item that cannot be used yet is DISABLED WITH A REASON, never hidden: it
 * stays in the menu, is focusable, carries `aria-disabled`, and states why
 * ("Pick a client first"). A missing entry reads as "this product does not do
 * that"; a disabled one reads as "not yet".
 *
 * Never: render the menu closed-but-in-the-DOM (it would be reachable by Tab),
 * or fire `onSelect` for a disabled item.
 */
export default function NavGroup({ label, items, activeId, onSelect }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const triggerRef = useRef(null);
  const itemRefs = useRef([]);
  const menuId = useId();
  const active = items.some((item) => item.id === activeId);

  const close = useCallback((restoreFocus = true) => {
    setOpen(false);
    if (restoreFocus) triggerRef.current?.focus();
  }, []);

  const openAt = (index) => {
    setOpen(true);
    // Focus after the menu has rendered.
    requestAnimationFrame(() => itemRefs.current[index]?.focus());
  };

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (event) => {
      if (!rootRef.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [open]);

  const onTriggerKeyDown = (event) => {
    if (event.key === 'ArrowDown') { event.preventDefault(); openAt(0); }
    else if (event.key === 'ArrowUp') { event.preventDefault(); openAt(items.length - 1); }
    else if (event.key === 'Escape' && open) { event.preventDefault(); event.stopPropagation(); close(); }
  };

  // A click that came from the keyboard (Enter/Space) opens onto the first item;
  // a pointer click leaves focus where the pointer put it.
  const onTriggerClick = (event) => {
    if (open) { close(false); return; }
    if (event.detail === 0) openAt(0);
    else setOpen(true);
  };

  const onMenuKeyDown = (event) => {
    const index = itemRefs.current.findIndex((node) => node === document.activeElement);
    const last = items.length - 1;
    const go = (next) => { event.preventDefault(); itemRefs.current[next]?.focus(); };
    if (event.key === 'ArrowDown') go(index >= last ? 0 : index + 1);
    else if (event.key === 'ArrowUp') go(index <= 0 ? last : index - 1);
    else if (event.key === 'Home') go(0);
    else if (event.key === 'End') go(last);
    else if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(); }
    else if (event.key === 'Tab') close(false);
  };

  const choose = (item) => {
    if (item.disabled) return;
    close(false);
    onSelect(item.id);
  };

  return (
    <div className="shell-group" ref={rootRef}>
      <button
        ref={triggerRef}
        type="button"
        className={`shell-group-trigger${active ? ' is-active' : ''}`}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={onTriggerClick}
        onKeyDown={onTriggerKeyDown}
      >
        {label}
        <ChevronDown size={14} aria-hidden="true" />
      </button>
      {open ? (
        <div id={menuId} role="menu" aria-label={label} className="shell-menu" onKeyDown={onMenuKeyDown}>
          {items.map((item, index) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                ref={(node) => { itemRefs.current[index] = node; }}
                type="button"
                role="menuitem"
                className={`shell-menu-item${item.id === activeId ? ' is-active' : ''}`}
                aria-current={item.id === activeId ? 'page' : undefined}
                aria-disabled={item.disabled || undefined}
                title={item.disabled ? item.reason : undefined}
                onClick={() => choose(item)}
              >
                {Icon ? <Icon size={16} aria-hidden="true" /> : null}
                <span className="shell-menu-label">{item.label}</span>
                {item.disabled && item.reason ? <span className="shell-menu-reason">{item.reason}</span> : null}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
