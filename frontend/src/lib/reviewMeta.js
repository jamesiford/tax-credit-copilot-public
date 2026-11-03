/**
 * Wording for the review header's meta line. Pure, so the header only lays out.
 */

const METHODS = { min_max: 'Min-Max', pay_period: 'Pay Period' };

export function methodLabel(method) {
  return METHODS[method] ?? null;
}

/** A run by the first characters of its id: enough to tell two apart. */
export function runLabel(run) {
  const id = run?.run_id;
  return id ? String(id).slice(0, 12) : null;
}

/**
 * `rule_pack_version` is a PATH ("rules/ga_jtc/2023.json"), and says which file
 * priced the run. The program and year are what a reader needs.
 */
export function rulePackLabel(version) {
  if (!version) return null;
  const parts = String(version).replace(/\\/g, '/').replace(/\.json$/, '').split('/').filter(Boolean);
  return parts.slice(-2).join('/') || null;
}
