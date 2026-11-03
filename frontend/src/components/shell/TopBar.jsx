import { brand } from '../../brand.config.js';
import NavGroup from './NavGroup.jsx';
import './shell.css';

/**
 * The top bar: brand, the navigation groups, and the right-hand cluster.
 *
 * `groups` is built from the app's NAV by `lib/shellNav.js`; this renders it. A
 * group with a single entry is a direct link rather than a one-item menu,
 * because a dropdown with one choice is a click spent on nothing.
 *
 * Never: know which routes exist, or decide what is disabled.
 */
export default function TopBar({ groups, activeId, onSelect, onHome, children }) {
  return (
    <div className="shell-bar">
      <button type="button" className="shell-brand" onClick={onHome} aria-label={`${brand.name}: the book`}>
        <img src={brand.logoSrc} alt="" />
        <span>{brand.name}</span>
      </button>

      <nav className="shell-nav" aria-label="Primary">
        {groups.map((group) => (group.items.length === 1 ? (
          <button
            key={group.section}
            type="button"
            className={`shell-group-trigger${group.items[0].id === activeId ? ' is-active' : ''}`}
            aria-current={group.items[0].id === activeId ? 'page' : undefined}
            aria-disabled={group.items[0].disabled || undefined}
            title={group.items[0].disabled ? group.items[0].reason : undefined}
            onClick={() => !group.items[0].disabled && onSelect(group.items[0].id)}
          >
            {group.items[0].label}
          </button>
        ) : (
          <NavGroup
            key={group.section}
            label={group.section}
            items={group.items}
            activeId={activeId}
            onSelect={onSelect}
          />
        )))}
      </nav>

      <div className="shell-bar-end">{children}</div>
    </div>
  );
}
