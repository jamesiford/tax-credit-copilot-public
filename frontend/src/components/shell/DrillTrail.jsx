import { Building2, ChevronRight, Layers, MapPin, UserSquare2, Users } from 'lucide-react';
import { atPortfolio, drillRungs } from '../../lib/drill.js';
import './shell.css';

/**
 * Where you are, under the top bar: Portfolio -> Client -> Location ->
 * Eligibility -> Employee, derived from the ROUTE (lib/drill.js), never from
 * state of its own.
 *
 * An unreached rung reads as "you haven't got here yet", not "this is broken":
 * it is dimmed, it is NOT a button, and it says what to do next. A reached rung
 * shows its real name; the current one is `aria-current="page"` and is not a
 * button either (you are already there). At the book, with nothing below it
 * reached, the whole trail collapses to one quiet line so the fold is not paid
 * for twice.
 *
 * Never: render an unreached rung as a disabled button, or hold the "current"
 * rung in component state.
 */
const ICONS = {
  portfolio: Layers, client: Building2, unit: MapPin, eligibility: Users, employee: UserSquare2,
};

export default function DrillTrail({
  clientId, clientName, unitId, token, view,
  onOpenPortfolio, onOpenClient, onOpenUnit, onSelectView,
}) {
  const rungs = drillRungs({ clientId, clientName, unitId, token, view });
  const quiet = atPortfolio(rungs);

  const go = {
    portfolio: onOpenPortfolio,
    client: onOpenClient,
    unit: onOpenUnit,
    eligibility: () => onSelectView?.('eligibility'),
    employee: null, // reached only by opening one; there is no "the" employee
  };

  if (quiet) {
    return (
      <nav className="shell-trail shell-trail-quiet" aria-label="Where you are">
        <ol>
          <li className="shell-rung current" aria-current="page">
            <span className="shell-rung-body">
              <Layers size={14} aria-hidden="true" />
              <span className="shell-rung-label">Portfolio</span>
            </span>
          </li>
        </ol>
        <span className="shell-trail-hint">choose a client to drill in</span>
      </nav>
    );
  }

  return (
    <nav className="shell-trail" aria-label="Where you are">
      <ol>
        {rungs.map((rung, index) => {
          const Icon = ICONS[rung.key];
          const onClick = go[rung.key];
          // Reached and navigable -> a button. Anything else -> plain text. A
          // control that looks clickable and is not is the thing this must
          // never do.
          const clickable = rung.reached && typeof onClick === 'function' && !rung.current;
          const cls = ['shell-rung', rung.reached ? 'reached' : 'pending', rung.current ? 'current' : '']
            .filter(Boolean).join(' ');
          const body = (
            <>
              <Icon size={14} aria-hidden="true" />
              <span className="shell-rung-label">{rung.label}</span>
            </>
          );
          return (
            <li key={rung.key} className={cls} aria-current={rung.current ? 'page' : undefined}>
              {index > 0 ? <ChevronRight size={14} className="shell-rung-sep" aria-hidden="true" /> : null}
              {clickable
                ? <button type="button" onClick={onClick}>{body}</button>
                : <span className="shell-rung-body">{body}</span>}
              {!rung.reached && rung.hint ? <span className="shell-rung-hint">{rung.hint}</span> : null}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
