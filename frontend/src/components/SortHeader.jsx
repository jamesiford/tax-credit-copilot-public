import { ColumnFilter } from './ColumnFilter.jsx';

/**
 * A sortable column header, optionally carrying that column's filter.
 *
 * Lifted out of `TrendGridView`, where it was first written, because the book
 * and the position grid need the same control. A second implementation is how
 * a click means one thing on one grid and something else on another — the same
 * reason `gridFilter.js` is written once and shared.
 *
 * `sort` is always an ARRAY of `{ key, desc }`, even where the caller only
 * supports one key. A grid sorting server-side passes a single-entry array and
 * gets the identical control; the shift-click affordance is hidden for it,
 * because offering a second key that the server will ignore is worse than not
 * offering it.
 */
export default function SortHeader({
  label, sortKey, sort, onSort, className, spec, filters, onFilter, options, multi = true,
}) {
  const active = sort.find((entry) => entry.key === sortKey);
  const rank = sort.findIndex((entry) => entry.key === sortKey);
  return (
    <th className={className} aria-sort={active ? (active.desc ? 'descending' : 'ascending') : 'none'}>
      <button
        type="button"
        className={`th-sort${active ? ' active' : ''}`}
        onClick={(event) => onSort(sortKey, { additive: multi && event.shiftKey })}
        title={multi ? 'Click to sort. Shift-click to add a second key.' : 'Click to sort.'}
      >
        {label}
        {active ? <span aria-hidden="true">{active.desc ? '\u25be' : '\u25b4'}</span> : null}
        {multi && sort.length > 1 && rank >= 0 ? <sup>{rank + 1}</sup> : null}
      </button>
      {spec ? (
        <ColumnFilter
          spec={spec}
          value={filters[spec.key] || ''}
          options={options || []}
          onChange={(expr) => onFilter(spec.key, expr)}
        />
      ) : null}
    </th>
  );
}
