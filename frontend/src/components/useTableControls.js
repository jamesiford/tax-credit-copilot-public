import { useCallback, useMemo, useState } from 'react';
import { presentValues } from '../lib/gridFilter.js';
import { arrangeRows, toggleKey } from '../lib/tableSort.js';

/**
 * Sort and filter state for one table, and the props its headers need.
 *
 *   const t = useTableControls(COLUMNS, rows);
 *   <SortHeader {...t.head('employee_id')} />
 *   <FilterBar {...t.bar('employees')} />
 *   {t.rows.map(...)}
 *
 * State is the component's own. The three page grids keep theirs in the URL
 * so a driven view can be shared; these are the tables inside a page, several
 * to a screen, and a query string carrying all of them would read as noise.
 *
 * A filter narrows the LIST, never the answer above it: `t.total` is the
 * unfiltered count, and headline figures must keep reading the payload.
 */
export default function useTableControls(columns, rows, { initialSort = [] } = {}) {
  const [sort, setSort] = useState(initialSort);
  const [filters, setFilters] = useState({});
  const source = rows || [];

  const shown = useMemo(
    () => arrangeRows(source, columns, { sort, filters }),
    [source, columns, sort, filters],
  );

  const onSort = useCallback((key, { additive = false } = {}) => {
    setSort((current) => toggleKey(current, key, { additive }));
  }, []);

  const onFilter = useCallback((key, expr) => {
    setFilters((current) => {
      const next = { ...current };
      if (String(expr ?? '').trim()) next[key] = expr;
      else delete next[key];
      return next;
    });
  }, []);

  const clear = useCallback((key) => {
    if (key == null) setFilters({});
    else onFilter(key, '');
  }, [onFilter]);

  /** Everything a `SortHeader` needs for one column. */
  const head = (key, extra = {}) => {
    const column = columns[key];
    const filterable = column.filterable !== false;
    const enumLike = column.type === 'enum' || column.type === 'year';
    return {
      label: column.label,
      sortKey: key,
      sort: column.sortable === false ? [] : sort,
      onSort: column.sortable === false ? () => {} : onSort,
      spec: filterable ? column : undefined,
      filters,
      onFilter,
      options: filterable && enumLike ? presentValues(source, column.read) : [],
      ...extra,
    };
  };

  /** Everything a `FilterBar` needs. */
  const bar = (noun) => ({
    specs: columns, filters, shown: shown.length, total: source.length, noun, onClear: clear,
  });

  return {
    rows: shown, total: source.length, sort, filters, onSort, onFilter, clear, head, bar,
  };
}
