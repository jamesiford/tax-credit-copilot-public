import { useCallback, useMemo } from 'react';
import FootprintMap from './FootprintMap.jsx';
import { footprintOf, selectedStates } from '../lib/bookCards.js';

/**
 * Where the book operates: the map and the list beside it.
 *
 * Clicking a state TOGGLES it in the shared filter grammar. Neither the map nor
 * the list holds a selection of its own: if they did, a chip cleared from the
 * filter bar would leave the map still looking selected.
 *
 * The map is two thirds whitespace on its own (we hold four states and the
 * other forty-six are the picture). The list fills it with the thing the map is
 * a control for, and gives the same filter a keyboard can reach.
 */
export default function FootprintPanel({ rows, filters, onFilter }) {
  const footprint = useMemo(() => footprintOf(rows), [rows]);
  const selected = useMemo(() => selectedStates(filters), [filters]);

  const toggleState = useCallback((code) => {
    const next = selected.includes(code)
      ? selected.filter((s) => s !== code)
      : [...selected, code];
    onFilter({ ...filters, state: next.join('|') });
  }, [filters, onFilter, selected]);

  return (
    <div className="tcc-footprint-row">
      <FootprintMap
        states={footprint.held}
        priced={footprint.priced}
        selected={selected}
        onSelect={toggleState}
      />
      <div className="tcc-footprint-list">
        <table className="tbl-compact">
          <thead>
            <tr>
              <th>State</th>
              <th className="num">Clients</th>
              <th>Statute</th>
            </tr>
          </thead>
          <tbody>
            {footprint.rows.map((s) => {
              const on = selected.includes(s.code);
              return (
                <tr key={s.code} className={on ? 'row-open' : undefined}>
                  <td>
                    <button
                      type="button"
                      className="tcc-cell-btn tcc-state-btn"
                      aria-pressed={on}
                      onClick={() => toggleState(s.code)}
                    >
                      {s.code}
                    </button>
                  </td>
                  <td className="num">{s.clients}</td>
                  <td className={s.priceable ? undefined : 'muted'}>
                    {s.priceable ? 'Priced' : 'No authored statute'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className="small muted">
          Clients, not dollars. A claim is client-grain and a client operates in
          several states, so a per-state total would either double-count or
          credit a state that did not earn it.
        </p>
        <p className="small muted">
          Selecting a state writes the same <code>state:</code> filter the bar
          shows, so the map, this list and the chips cannot disagree.
        </p>
      </div>
    </div>
  );
}
