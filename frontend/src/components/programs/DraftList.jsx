/*
 * Why: drafts are working material, so they have their own list: what is open, in what state, last changed by whom. Reading them
 * needs the writer role; a refusal says so rather than showing an empty list that looks like "no drafts".
 * Never: show a withdrawn or exported draft as if it were open (its status is on the row).
 */
import { useEffect, useState } from 'react';
import { listProgramDrafts } from '../../api.js';
import { ENUM, TEXT } from '../../lib/gridFilter.js';
import { DRAFT_STATUS_LABEL } from '../../lib/programs.js';
import { FilterBar } from '../ColumnFilter.jsx';
import SortHeader from '../SortHeader.jsx';
import useTableControls from '../useTableControls.js';
import EmptyState from '../ui/EmptyState.jsx';
import Skeleton from '../ui/Skeleton.jsx';
import { DraftStatusBadge } from './Badges.jsx';

const columns = {
  name: { key: 'name', label: 'Draft', type: TEXT, read: (d) => `${d.name} ${d.proposed_code}` },
  state: { key: 'state', label: 'State', type: ENUM, read: (d) => d.state },
  status: { key: 'status', label: 'Status', type: ENUM, read: (d) => DRAFT_STATUS_LABEL[d.status] || d.status },
  updated: { key: 'updated', label: 'Last changed', type: TEXT, read: (d) => d.updated_at, filterable: false },
};
const when = (iso) => (iso ? iso.replace('T', ' ').slice(0, 16) : '\u2014');

function Table({ items, onOpen }) {
  const table = useTableControls(columns, items, { initialSort: [{ key: 'updated', desc: true }] });
  return (
    <>
      <FilterBar {...table.bar('drafts')} />
      <table className="tbl" aria-label="Program drafts">
        <thead><tr>
          <SortHeader {...table.head('name')} /><SortHeader {...table.head('state')} /><SortHeader {...table.head('status')} />
          <th>Errors</th><SortHeader {...table.head('updated')} /><th>By</th>
        </tr></thead>
        <tbody>
          {table.rows.map((d) => (
            <tr key={d.draft_id}>
              <td><button type="button" className="tcc-link" onClick={() => onOpen(d.draft_id)} aria-label={`Open draft ${d.name}`}>{d.name}</button>
                <div className="small muted"><code>{d.proposed_code}</code></div></td>
              <td>{d.state}</td>
              <td><DraftStatusBadge status={d.status} /></td>
              <td className="small">{d.validation_errors ?? 'not validated'}</td>
              <td className="small">{when(d.updated_at)}</td>
              <td className="small">{d.updated_by}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

export default function DraftList({ onOpen, onNew }) {
  const [state, setState] = useState({ loading: true, data: null, error: null });
  useEffect(() => {
    let cancelled = false;
    listProgramDrafts({ limit: 100 })
      .then((data) => { if (!cancelled) setState({ loading: false, data, error: null }); })
      .catch((error) => { if (!cancelled) setState({ loading: false, data: null, error }); });
    return () => { cancelled = true; };
  }, []);
  if (state.loading) return <Skeleton lines={4} label="Loading drafts" />;
  if (state.error) {
    return (
      <EmptyState title={state.error.status === 403 ? 'Drafts need the writer role' : 'Drafts are unavailable'}>
        {state.error.reason || state.error.message} Nothing was changed; the catalog is unaffected.
      </EmptyState>
    );
  }
  const items = state.data.items || [];
  if (!items.length) {
    return (
      <EmptyState title="No drafts yet" action={<button type="button" className="tcc-link" onClick={onNew}>Add a program</button>}>
        A draft is a proposal to bring on a new program. Start one to scaffold its pack, then validate, preview, review and export it.
      </EmptyState>
    );
  }
  return <Table items={items} onOpen={onOpen} />;
}
