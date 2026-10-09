import { ChevronRight } from 'lucide-react';

/**
 * Where this page sits, derived from the route rather than from memory.
 *
 * The drill used to be overlays, so there was nothing to be lost in — you were
 * always on the page behind. Now that each level is its own URL, a viewer three
 * levels down needs to see the path they took and be able to walk back up it.
 */
export default function Breadcrumb({ trail }) {
  const crumbs = (trail || []).filter(Boolean);
  if (crumbs.length < 2) return null;
  return (
    <nav className="tcc-breadcrumb" aria-label="Breadcrumb">
      {crumbs.map((crumb, index) => {
        const last = index === crumbs.length - 1;
        return (
          <span key={crumb.key ?? crumb.label} className="tcc-crumb">
            {index > 0 ? <ChevronRight size={13} aria-hidden="true" /> : null}
            {!last && crumb.onClick
              ? <button type="button" className="tcc-link" onClick={crumb.onClick}>{crumb.label}</button>
              : <b aria-current={last ? 'page' : undefined}>{crumb.label}</b>}
            {/* A fact about this level, beside its name — the client's industry. */}
            {crumb.badge ? <span className="tcc-crumb-badge">{crumb.badge}</span> : null}
          </span>
        );
      })}
    </nav>
  );
}
