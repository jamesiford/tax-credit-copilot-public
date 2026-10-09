import {
  Binary, BookOpenCheck, Building2, ClipboardList, Database, MapPin,
  ShieldCheck, ShieldQuestion, Users, UserSquare2, Layers,
} from 'lucide-react';

/**
 * The left rail: where you are, and what proves the work.
 *
 * Two sections, and they answer different questions.
 *
 * **The drill** is a vertical breadcrumb, not a menu. The partner's own
 * framing of the product is an accordion — *"Portfolio -> Legal Entity -> State
 * -> Location or Unit -> Employee -> Payroll Record... at every level the user
 * remains only one or two clicks away from the supporting detail"* — and until
 * now that shape was only visible AFTER you had drilled into it, as a
 * horizontal breadcrumb. On the rail it is on screen from the first second, so
 * a viewer sees the shape of the product before anybody describes it.
 *
 * **Prove the work** is flat and always available. It exists because a demo
 * cannot click everything: an entry nobody opens still says *we thought about
 * this*. Shashi Bhushan, 21 Sep: *"We don't have time to speak to it, but it's
 * there. They can see it... otherwise it looks like another vibe-coding effort.
 * This is a real application."*
 *
 * ## The rule that makes the drill work
 *
 * An unreached rung must read as **"you haven't got here yet"**, never as
 * **"this is broken"**. Three things carry that distinction:
 *
 *   - a REACHED rung shows the real name — "Ironbridge Logistics", not the
 *     generic word "Client";
 *   - the CURRENT rung is marked;
 *   - an unreached rung is dimmed, is NOT a button, and says what to do next.
 *
 * Rendered that way it is a progress ladder that teaches the hierarchy.
 * Rendered as greyed-out buttons it looks like a half-built app, which is the
 * one impression this rail exists to prevent.
 *
 * The ladder is derived from the ROUTE, never from separate state, so the rail
 * and the page it sits beside cannot disagree about where you are.
 */

export const GOVERNANCE = [
  { id: 'ingestion', label: 'Payroll data', icon: Database },
  { id: 'rules', label: 'Programs', icon: BookOpenCheck },
  { id: 'assumptions', label: 'Calculations', icon: ShieldCheck },
  { id: 'onezero', label: 'Monthly employment', icon: Binary },
  { id: 'agents', label: 'Agents', icon: ShieldQuestion },
  { id: 'evidence', label: 'Audit trail', icon: ClipboardList },
];

/**
 * The five rungs, resolved against the current route.
 *
 * `eligibility` is the rung between Unit and Employee: it is the employee
 * cohort for a client-year — who qualifies, and who is near the line — which
 * is exactly what sits there. It is a nav destination rather than a route
 * segment, so it is "reached" when it is the active view.
 */
export function drillRungs({ clientId, clientName, unitId, token, view }) {
  const hasClient = clientId != null && clientId !== 'portfolio';
  const onEligibility = view === 'eligibility';

  return [
    {
      key: 'portfolio',
      label: 'Portfolio',
      icon: Layers,
      reached: true,
      current: !hasClient && !onEligibility,
      hint: null,
    },
    {
      key: 'client',
      label: hasClient ? (clientName || `Account ${clientId}`) : 'Client',
      icon: Building2,
      reached: hasClient,
      current: hasClient && !unitId && !token && !onEligibility,
      hint: 'pick a client from the book',
    },
    {
      key: 'unit',
      label: unitId || 'Location',
      icon: MapPin,
      reached: Boolean(unitId),
      current: Boolean(unitId) && !token,
      hint: 'open a year on a location',
    },
    {
      key: 'eligibility',
      label: 'Eligibility',
      icon: Users,
      reached: hasClient,
      current: onEligibility,
      hint: 'pick a client first',
    },
    {
      key: 'employee',
      label: 'Employee',
      icon: UserSquare2,
      reached: Boolean(token),
      current: Boolean(token),
      hint: 'open an employee\u2019s walk',
    },
  ];
}

export default function SideRail({
  clientId, clientName, unitId, token, view,
  onOpenPortfolio, onOpenClient, onOpenUnit, onSelectView,
  open = false, onClose,
}) {
  const rungs = drillRungs({ clientId, clientName, unitId, token, view });

  const go = {
    portfolio: onOpenPortfolio,
    client: onOpenClient,
    unit: onOpenUnit,
    eligibility: () => onSelectView('eligibility'),
    employee: null, // reached only by opening one; there is no "the" employee
  };

  return (
    <aside className={`tcc-siderail ${open ? 'open' : ''}`} aria-label="Navigation">
      <nav className="tcc-rail-drill" aria-label="Where you are">
        <div className="tcc-rail-section">Where you are</div>
        <ol>
          {rungs.map((rung, depth) => {
            const Icon = rung.icon;
            const onClick = go[rung.key];
            // Reached and navigable -> a button. Reached but not navigable, or
            // not reached at all -> plain text. A control that looks clickable
            // and is not is the thing this rail must never do.
            const clickable = rung.reached && typeof onClick === 'function' && !rung.current;
            const className = [
              'tcc-rung',
              `depth-${depth}`,
              rung.reached ? 'reached' : 'pending',
              rung.current ? 'current' : '',
            ].filter(Boolean).join(' ');

            const body = (
              <>
                <span className="tcc-rung-rail" aria-hidden="true" />
                <Icon size={15} />
                <span className="tcc-rung-label">{rung.label}</span>
              </>
            );

            return (
              <li key={rung.key} className={className}>
                {clickable ? (
                  <button type="button" onClick={onClick}>{body}</button>
                ) : (
                  <div aria-current={rung.current ? 'page' : undefined}>{body}</div>
                )}
                {!rung.reached && rung.hint && (
                  <span className="tcc-rung-hint">{rung.hint}</span>
                )}
              </li>
            );
          })}
        </ol>
      </nav>

      <nav className="tcc-rail-gov" aria-label="Prove the work">
        <div className="tcc-rail-section">Prove the work</div>
        {GOVERNANCE.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              type="button"
              className={view === item.id ? 'active' : ''}
              onClick={() => { onSelectView(item.id); onClose?.(); }}
            >
              <Icon size={15} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="tcc-rail-footer">
        <ShieldCheck size={15} />
        <span>
          <b>Deterministic core</b>
          <small>Agents narrate. Tools calculate.</small>
        </span>
      </div>
    </aside>
  );
}
