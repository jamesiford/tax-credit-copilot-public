/*
 * Why: the catalog answers "what does the platform know, what can it calculate and why not". Sorting and filtering follow the
 * one table grammar; the lifecycle, the authored years, the unverified flags and the reason a program cannot be calculated are
 * all on the row, so nothing needs a second click to be honest.
 * Never: say a program is verified, or show a described program as if it could be run (it is disabled WITH its reason).
 */
import { useMemo } from 'react';
import { FilterBar } from '../ColumnFilter.jsx';
import SortHeader from '../SortHeader.jsx';
import useTableControls from '../useTableControls.js';
import EmptyState from '../ui/EmptyState.jsx';
import { ENUM, NUMERIC, TEXT } from '../../lib/gridFilter.js';
import { engagementLabel, lifecycleLabel, unverifiedLabel, yearsLabel } from '../../lib/programs.js';
import { LifecycleBadge, NotVerified } from './Badges.jsx';

const columns = {
  name: { key: 'name', label: 'Program', type: TEXT, read: (r) => `${r.name} ${r.code}` },
  state: { key: 'state', label: 'State', type: ENUM, read: (r) => r.state || r.jurisdiction?.level },
  lifecycle: { key: 'lifecycle', label: 'Lifecycle', type: ENUM, read: (r) => lifecycleLabel(r) },
  years: { key: 'years', label: 'Authored years', type: NUMERIC, read: (r) => (r.authored_years || []).length },
  calculable: { key: 'calculable', label: 'Calculable', type: ENUM, read: (r) => (r.calculable ? 'Yes' : 'No') },
  clients: { key: 'clients', label: 'Clients', type: NUMERIC, read: (r) => r.engagement?.clients ?? null },
};

export default function ProgramCatalog({ rows, onOpen }) {
  const table = useTableControls(columns, rows, { initialSort: [] });
  const empty = useMemo(() => !rows?.length, [rows]);
  if (empty) {
    return (
      <EmptyState title="No programs are registered">
        The registry lists no programs, so nothing can be calculated. Programs arrive as a registry entry plus authored year packs in git.
      </EmptyState>
    );
  }
  return (
    <>
      <FilterBar {...table.bar('programs')} />
      <table className="tbl prog-catalog" aria-label="Program catalog">
        <thead>
          <tr>
            <SortHeader {...table.head('name')} />
            <SortHeader {...table.head('state')} />
            <SortHeader {...table.head('lifecycle')} />
            <SortHeader {...table.head('years')} />
            <th>Verification</th>
            <SortHeader {...table.head('calculable')} />
            <SortHeader {...table.head('clients')} className="num" />
          </tr>
        </thead>
        <tbody>
          {table.rows.map((r) => (
            <tr key={r.code}>
              <td>
                <button type="button" className="tcc-link" onClick={() => onOpen(r.code)} aria-label={`Open ${r.name}`}>{r.name}</button>
                <div className="small muted"><code>{r.code}</code></div>
              </td>
              <td>{r.state || r.jurisdiction?.level}</td>
              <td><LifecycleBadge lifecycle={r.lifecycle} /></td>
              <td className="small">{yearsLabel(r.authored_years)}</td>
              <td className="small"><NotVerified>{unverifiedLabel(r)}</NotVerified></td>
              <td className="small">
                {r.calculable ? 'Yes' : <span title={r.not_calculable_reason}>No: {r.not_calculable_reason}</span>}
              </td>
              <td className="num small">{engagementLabel(r.engagement)}</td>
            </tr>
          ))}
          {!table.rows.length && (
            <tr><td colSpan={7}><EmptyState title="No program matches the filters">Clear a filter to see the rest.</EmptyState></td></tr>
          )}
        </tbody>
      </table>
    </>
  );
}
