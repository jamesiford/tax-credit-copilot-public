/**
 * Gold tables → the shape the location grid renders.
 *
 * `/api/v2/clients/{id}/units` returns three Gold tables as themselves:
 * `items` (unit_year_master), `months` (unit_month_summary) and `installments`
 * (unit_credit_installment, already summed per claimable year in SQL). The grid
 * draws one block per location with a row per year, so the rows have to be
 * grouped.
 *
 * This is GROUPING, not translation. Field names stay exactly as the warehouse
 * spells them — `net_new_vs_base`, not `net_new` — so there is one vocabulary
 * between the SQL and the screen. The only added key is `unit_id`, which mirrors
 * `worksite_id` because it is the React key and the join handle the drill uses.
 *
 * No arithmetic happens here. Every dollar arrives summed from SQL, because
 * adding money in a browser means adding it as a float.
 */

const MONTH_KEYS = Array.from({ length: 12 }, (_, i) => `month_${String(i + 1).padStart(2, '0')}`);

/** The twelve monthly cells of a `unit_month_summary` row, in order. */
export function monthTotals(summary) {
  if (!summary) return Array(12).fill(0);
  return MONTH_KEYS.map((key) => Number(summary[key] ?? 0));
}

/** `"10,11"` as stored → `[10, 11]`. Empty when nothing is unreachable. */
export function unreachableMonths(summary) {
  const raw = summary?.unreachable_months;
  if (!raw) return [];
  return String(raw)
    .split(',')
    .map((part) => Number(part.trim()))
    .filter((value) => Number.isInteger(value));
}

/**
 * One payload from `/api/v2/clients/{id}/units` → `{ units, years, year_meta }`.
 *
 * Returns `units: []` for a client with no run. The caller must branch on
 * `calculation_state` BEFORE rendering: an empty grid and "not yet calculated"
 * are different statements, and only one of them is about the payroll.
 */
export function trendFromGold(payload) {
  const items = payload?.items || [];
  if (!items.length) return { units: [], years: [], year_meta: [], totals: {} };

  const monthsByKey = new Map(
    (payload.months || []).map((m) => [`${m.worksite_id}|${m.tax_year}`, m]),
  );
  const dimensionByUnit = new Map(
    (payload.units || []).map((u) => [u.worksite_id, u]),
  );
  const totalsByUnit = new Map(
    (payload.unit_totals || []).map((t) => [t.worksite_id, t]),
  );

  const creditsByUnit = new Map();
  for (const column of payload.installments || []) {
    const list = creditsByUnit.get(column.worksite_id) || [];
    list.push(column);
    creditsByUnit.set(column.worksite_id, list);
  }

  const rowsByUnit = new Map();
  for (const item of items) {
    const summary = monthsByKey.get(`${item.worksite_id}|${item.tax_year}`);
    const list = rowsByUnit.get(item.worksite_id) || [];
    list.push({
      ...item,
      month_totals: monthTotals(summary),
      total: Number(summary?.total ?? 0),
      months_with_headcount: summary?.months_with_headcount ?? 0,
    });
    rowsByUnit.set(item.worksite_id, list);
  }

  const units = [...rowsByUnit.entries()].map(([worksiteId, rows]) => {
    rows.sort((a, b) => a.tax_year - b.tax_year);
    const baseRow = rows.find((row) => row.is_base_year) || null;
    const latest = rows[rows.length - 1];
    const dimension = dimensionByUnit.get(worksiteId) || {};
    const totals = totalsByUnit.get(worksiteId) || {};

    return {
      // `unit_id` mirrors `worksite_id`: the React key and the drill's handle.
      unit_id: worksiteId,
      worksite_id: worksiteId,
      name: dimension.name || worksiteId,
      county: dimension.county || '',
      city: dimension.city || '',
      feins: [...new Set(rows.map((row) => row.entity_fein).filter(Boolean))],
      base_year: baseRow ? baseRow.tax_year : null,
      base_year_source: latest.base_year_source,
      base_average_headcount: Number(latest.base_average_headcount ?? 0),
      threshold: latest.threshold,
      threshold_source: latest.threshold_source,
      per_job_usd: latest.per_job_usd,
      tranche_years: latest.tranche_years,
      rows,
      credit_years: (creditsByUnit.get(worksiteId) || [])
        .slice()
        .sort((a, b) => a.tax_year - b.tax_year),
      total_annual_credit_usd: Number(totals.total_annual_credit_usd ?? 0),
      total_tranche_lifetime_usd: Number(totals.total_tranche_lifetime_usd ?? 0),
      final_high_water_mark: Number(totals.final_high_water_mark ?? 0),
    };
  });

  const years = [...new Set(items.map((item) => item.tax_year))].sort((a, b) => a - b);
  const year_meta = years.map((taxYear) => {
    const anySummary = (payload.months || []).find((m) => m.tax_year === taxYear);
    const anyItem = items.find((item) => item.tax_year === taxYear);
    return {
      tax_year: taxYear,
      unreachable_months: unreachableMonths(anySummary),
      months_reachable: anyItem?.months_reachable ?? 12,
    };
  });

  return {
    units,
    years,
    year_meta,
    totals: {
      annual_credit_usd: (payload.unit_totals || [])
        .reduce((sum, t) => sum + Number(t.total_annual_credit_usd ?? 0), 0),
      tranche_lifetime_usd: (payload.unit_totals || [])
        .reduce((sum, t) => sum + Number(t.total_tranche_lifetime_usd ?? 0), 0),
    },
    program_code: items[0]?.program_code,
  };
}
