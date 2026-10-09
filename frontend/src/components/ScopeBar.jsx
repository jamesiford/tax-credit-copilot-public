import { useMemo } from 'react';
import { Building2, CalendarRange, Landmark, Layers, Loader2, TriangleAlert } from 'lucide-react';
import {
  ALL_PROGRAMS, PORTFOLIO, derivedJurisdictions, placeholderYears, unpriceableYears,
} from '../lib/scopeDimension.js';

/**
 * The persistent scope bar: client x program x year.
 *
 * Three controls and one line of derived consequence. The consequence line is
 * the point — a selector that shows only what you picked is a facade, and this
 * one has to show what the pick MEANS: which jurisdictions are in play, which
 * years can be priced, and which years we hold payroll for but cannot.
 */
export default function ScopeBar({
  options, scope, resolved, clientScope, clientError, clientLoading, onChange, loading,
}) {
  const jurisdictions = useMemo(
    () => derivedJurisdictions(scope, options),
    [scope, options],
  );
  const unpriceable = unpriceableYears(clientScope);
  const placeholder = placeholderYears(options, scope.programCode);
  const openYears = new Set(clientScope?.open_years || []);
  const years = resolved?.availableYears || [];
  const windowYears = resolved?.window || [];
  const narrowed = scope.clientId !== PORTFOLIO;

  const set = (patch) => onChange({ ...scope, ...patch });

  return (
    <div className="scope-bar" role="region" aria-label="Scope">
      <div className="scope-axes">
        <label className="scope-axis">
          <span className="scope-axis-label"><Building2 size={14} /> Who</span>
          <select
            value={String(scope.clientId)}
            disabled={loading}
            onChange={(e) => set({ clientId: e.target.value === PORTFOLIO ? PORTFOLIO : Number(e.target.value) })}
          >
            <option value={PORTFOLIO}>All clients ({(options?.clients || []).length})</option>
            {(options?.clients || []).map((c) => (
              <option key={c.account_id} value={c.account_id}>
                {c.name}{c.synthetic ? ' \u00b7 synthetic' : ''}
              </option>
            ))}
          </select>
        </label>

        <label className="scope-axis">
          <span className="scope-axis-label"><Layers size={14} /> What</span>
          <select
            value={scope.programCode}
            disabled={loading}
            onChange={(e) => set({ programCode: e.target.value })}
          >
            <option value={ALL_PROGRAMS}>All programs</option>
            {(options?.programs || []).map((p) => (
              <option key={p.program_code} value={p.program_code} disabled={!p.calculable}>
                {p.name}{p.calculable ? '' : ' \u2014 no authored years'}
              </option>
            ))}
          </select>
        </label>

        <label className="scope-axis">
          <span className="scope-axis-label"><CalendarRange size={14} /> When</span>
          <div className="scope-when">
            <select
              value={scope.year ?? ''}
              disabled={loading || clientLoading || !years.length}
              onChange={(e) => set({ year: Number(e.target.value) })}
            >
              {!years.length && <option value="">no priceable year</option>}
              {years.map((y) => {
                // A partial year is labelled as one. Selecting it silently and
                // then rendering $0 makes an incomplete extract look like a
                // client who earned nothing.
                const months = clientScope?.months_of_payroll?.[y];
                const partial = months != null && months < 12;
                // An OPEN year is not a partial one: it is short because the
                // rest of it has not happened, and it says so.
                const label = openYears.has(y)
                  ? `TY${y} · open, ${months ?? 0}mo in`
                  : partial ? `TY${y} · ${months}mo` : `TY${y}`;
                return (
                  <option key={y} value={y}>{label}</option>
                );
              })}
            </select>
            <button
              type="button"
              className={`scope-window-toggle ${scope.windowMode ? 'on' : ''}`}
              disabled={loading || clientLoading || years.length < 2}
              aria-pressed={scope.windowMode}
              onClick={() => set({ windowMode: !scope.windowMode })}
              title="Retroactive window: a base year plus five"
            >
              {scope.windowMode && windowYears.length > 1
                ? `${windowYears[0]}\u2013${windowYears[windowYears.length - 1]}`
                : 'Window'}
            </button>
          </div>
        </label>
      </div>

      <div className="scope-derived">
        <span className="scope-derived-item" title="Derived from the selected program, never chosen separately">
          <Landmark size={13} />
          {jurisdictions.length
            ? jurisdictions.map((j) => j.code).join(' \u00b7 ')
            : 'no jurisdiction'}
          <em>derived</em>
        </span>

        {clientLoading && (
          <span className="scope-derived-item loading">
            <Loader2 size={13} className="spin" /> reading this client&apos;s payroll…
          </span>
        )}

        {!clientLoading && clientScope && (
          <span className="scope-derived-item">
            {clientScope.rows.toLocaleString()} payroll rows
            {clientScope.states?.length ? ` \u00b7 ${clientScope.states.join(', ')}` : ''}
          </span>
        )}

        {!clientLoading && narrowed && !clientScope && !clientError && (
          <span className="scope-derived-item">no payroll for this client</span>
        )}

        {!clientLoading && unpriceable.length > 0 && (
          <span className="scope-derived-item warn" title="Payroll exists for these years but no statute has been authored, so they cannot be calculated">
            <TriangleAlert size={13} />
            TY{unpriceable.join(', TY')} held, not priceable
          </span>
        )}

        {placeholder.includes(scope.year) && (
          <span
            className="scope-derived-item warn"
            title={`TY${scope.year}'s wage floor is not published yet. The TY${scope.year - 1} floor is carried forward as a placeholder until it is; every figure for TY${scope.year} rests on it.`}
          >
            <TriangleAlert size={13} />
            TY{scope.year} floor is a placeholder
          </span>
        )}

        {clientError && (
          <span className="scope-derived-item warn"><TriangleAlert size={13} />{clientError}</span>
        )}
      </div>

      {(resolved?.notices || []).length > 0 && (
        <ul className="scope-notices">
          {resolved.notices.map((n) => (
            <li key={`${n.axis}-${n.message}`}><TriangleAlert size={13} /> {n.message}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
