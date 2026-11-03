import { useEffect, useRef, useState } from 'react';
import { initials } from '../../lib/identity.js';
import TopScope from '../TopScope.jsx';
import './shell.css';

/**
 * The right-hand cluster of the top bar: the scope axis that applies on this
 * page, and the signed-in account.
 *
 * The account menu exists only when somebody IS signed in (AUTH_MODE=entra).
 * With AUTH_MODE=none there is no identity to show, and a menu that offers a
 * "guest" would be a control standing in for nothing, which is what
 * docs/architecture says to avoid: a name where an enforcement should be.
 *
 * Never: fetch anything itself, or offer an action (sign out, switch account)
 * the platform does not provide: Easy Auth owns that.
 */
export default function ShellActions({ scopeProps, identity }) {
  return (
    <div className="shell-actions">
      <TopScope {...scopeProps} />
      {identity?.authenticated ? <AccountMenu identity={identity} /> : null}
    </div>
  );
}

function AccountMenu({ identity }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const triggerRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (event) => { if (!ref.current?.contains(event.target)) setOpen(false); };
    const onKeyDown = (event) => {
      if (event.key === 'Escape') { setOpen(false); triggerRef.current?.focus(); }
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  return (
    <div className="shell-account" ref={ref}>
      <button
        ref={triggerRef}
        type="button"
        className="shell-avatar"
        aria-expanded={open}
        aria-label={`Account: ${identity.upn}`}
        onClick={() => setOpen((v) => !v)}
      >
        {initials(identity)}
      </button>
      {open ? (
        <div className="shell-popover" role="region" aria-label="Account">
          <div className="shell-popover-name">{identity.upn}</div>
          <div className="shell-popover-meta">Signed in · {identity.auth_mode || 'entra'}</div>
        </div>
      ) : null}
    </div>
  );
}
