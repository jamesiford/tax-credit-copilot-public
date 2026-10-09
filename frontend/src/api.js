// Same-origin in prod (frontend/server proxies /api/* to the API app).
// In dev, Vite proxies /api/* to http://localhost:8000.
// API base — empty by default so requests go through the Vite proxy in dev.
// Override with VITE_API_BASE for any non-proxied deployment (e.g. cloud
// frontend talking to a Container App backend).
const BASE = import.meta.env?.VITE_API_BASE ?? '';

async function workspaceRequest(path, options = {}) {
  const response = await fetch(`${BASE}/api/workspace${path}`, options);
  if (!response.ok) {
    let detail = '';
    try { detail = (await response.json())?.detail || ''; } catch { /* non-JSON error */ }
    throw new Error(`workspace ${response.status}${detail ? ` · ${detail}` : ''}`);
  }
  return response.json();
}

const jsonPost = (payload) => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(payload),
});

/**
 * Apply the client axis to a query string.
 *
 * `portfolio` is the ABSENCE of a client rather than a client id, so it is
 * omitted and the endpoint answers for its configured default. Every payroll-
 * reading endpoint takes `account_id`; sending the wrong one — or, as was true
 * until recently, sending one the router quietly discarded — puts one client's
 * figures under another client's name.
 */
export function withAccount(params, accountId) {
  if (accountId != null && accountId !== 'portfolio') {
    params.set('account_id', String(accountId));
  }
  return params;
}

/**
 * A tax year is a PATH segment, so an absent one is not an absent filter — it
 * is a different URL.
 *
 * `reconcileScope` returns `year: null` while a client's payroll is still
 * loading and whenever nothing can be priced. Interpolating that produced
 * `/api/ingestion/null`, which the router answers 422. Two things made it
 * worse than a single bad request: a JS default parameter (`taxYear = 2025`)
 * does not fire for `null`, so the fallback every one of these components
 * declared never applied; and the failed fetch re-ran on every render, which
 * logged 4,968 console errors on one client before the page settled.
 *
 * Refusing here turns an invalid URL into a named, catchable error at the one
 * place every caller passes through.
 */
/**
 * Is a tax year actually selected?
 *
 * Exported because components need the same answer BEFORE they fetch — the
 * guard below turns a bad call into an error, but a view that knows it has no
 * year yet should render a waiting state rather than an error message.
 *
 * `Number(null)` is 0 and `Number('')` is 0 — both finite — so the empty cases
 * have to be rejected before the numeric check, not by it.
 */
export function hasYear(taxYear) {
  return taxYear != null && taxYear !== '' && Number.isFinite(Number(taxYear));
}

function requireYear(taxYear, what) {
  if (!hasYear(taxYear)) {
    throw new Error(`${what} needs a tax year — none is selected yet`);
  }
  return Number(taxYear);
}

/** `?a=b` for a populated URLSearchParams, or '' — avoids a trailing bare `?`. */
const qs = (params) => (params.toString() ? `?${params}` : '');

export const fetchWorkspace = () => workspaceRequest('');
export const refreshWorkspace = () => workspaceRequest('/refresh', { method: 'POST' });
export const searchWorkspaceSource = (payload = {}) => workspaceRequest('/source/search', jsonPost(payload));
export const searchWorkspaceEligibility = (payload = {}) => workspaceRequest('/eligibility/search', jsonPost(payload));
export const fetchWorkspaceEmployee = (recordToken) => workspaceRequest('/employee', jsonPost({ record_token: recordToken }));
export const fetchWorkspaceOneZero = (method) => workspaceRequest(`/onezero/${encodeURIComponent(method)}`);
export const fetchWorkspaceContributors = (payload) => workspaceRequest('/onezero/contributors', jsonPost(payload));
export const fetchWorkspaceCalculationWalk = () => workspaceRequest('/calculation-walk');
export const fetchWorkspaceAssumptions = () => workspaceRequest('/assumptions');
export const fetchWorkspaceComparison = () => workspaceRequest('/comparison');
export const fetchWorkspaceComparisonStage = (stage) => workspaceRequest('/comparison/stage', jsonPost({ stage }));

/**
 * Who qualifies, for the SELECTED client — not the sealed run.
 *
 * The sealed `/api/workspace/eligibility/search` above answers for the certified
 * reference client and only that client. This one takes the scope, so the
 * population follows the selector like every other operational view.
 */
export async function fetchEligibility(taxYear, {
  state = 'GA', accountId, status = 'all', nearFloor = false, q = '', limit = 50, offset = 0,
  sort, order,
} = {}) {
  const params = new URLSearchParams({ state, status, limit: String(limit), offset: String(offset) });
  if (accountId != null) params.set('account_id', String(accountId));
  if (nearFloor) params.set('near_floor', 'true');
  if (q) params.set('q', q);
  // Ordered in SQL before the page is cut (29 Sep); a page sorted in the
  // browser would present 50 of 10,236 as the top of a list they are not.
  if (sort) params.set('sort', sort);
  if (order) params.set('order', order);
  const r = await fetch(`${BASE}/api/eligibility/${encodeURIComponent(taxYear)}${qs(params)}`);
  if (!r.ok) throw new Error(`eligibility ${r.status}`);
  return r.json();
}

/**
 * The One/Zero monthly matrix for the SELECTED client.
 *
 * Resolves the same fiscal window as `fetchEligibility`, so the two views
 * cannot disagree about the denominator period for one client-year.
 */
export async function fetchOneZeroMatrix(taxYear, { state = 'GA', accountId, method = 'min_max' } = {}) {
  const params = new URLSearchParams({ state, method });
  if (accountId != null) params.set('account_id', String(accountId));
  const r = await fetch(`${BASE}/api/onezero/matrix/${encodeURIComponent(taxYear)}${qs(params)}`);
  if (!r.ok) throw new Error(`onezero matrix ${r.status}`);
  return r.json();
}

/**
 * One employee's derivation for the SELECTED client-year.
 *
 * The sealed `fetchWorkspaceEmployee` resolves tokens against the certified run
 * only — account 1001, TY2023 — so a token minted for any other client-year is a
 * valid handle that resolves nowhere. This one resolves against the client-year
 * that produced it, by LOOKUP: `record_token` is a stored column on every
 * employee-grain Gold table. It used to re-mint a token for the whole
 * population and match, behind two engine replays. The handle goes in the
 * BODY: an employee never appears in a URL path.
 */
export async function fetchClientEmployeeDrill({ recordToken, taxYear, state = 'GA', accountId } = {}) {
  const body = { record_token: recordToken, tax_year: taxYear, state };
  if (accountId != null && accountId !== 'portfolio') body.account_id = Number(accountId);
  const r = await fetch(`${BASE}/api/employee/drill`, jsonPost(body));
  if (!r.ok) throw new Error(`employee drill ${r.status}`);
  return r.json();
}

// --- v2: the warehouse-backed read surface ---------------------------------
//
// Every figure on these comes from `tcc_gold`, written by a run. Nothing here
// triggers a calculation, so a client that has never been run answers
// `calculation_state: 'not_calculated'` with an empty `items` and a null `run`.
//
// THAT IS NOT A ZERO. With no bulk run it is the common state, and rendering it
// as $0 tells an operator the client has no payroll. `isCalculated` below is the
// one place that distinction is made, so a view cannot get it wrong by writing
// `!items.length`.

async function v2Request(path, options = {}) {
  const r = await fetch(`${BASE}/api/v2${path}`, options);
  if (!r.ok) {
    let detail = '';
    try { detail = (await r.json())?.detail || ''; } catch { /* non-JSON error */ }
    throw new Error(`v2 ${r.status}${detail ? ` · ${detail}` : ''}`);
  }
  return r.json();
}

/** True only when a run produced these figures. Empty + no run is NOT zero. */
export const isCalculated = (payload) => payload?.calculation_state === 'calculated';

/**
 * One row per client — the book.
 *
 * `priority` is descending call order expressed as an ASCENDING rank, so `asc`
 * is correct: band first, then identified dollars within the band. Pass
 * `sort: 'jobs_gap'` for the narrower "who is closest to qualifying" question.
 */
export async function fetchPortfolioV2({
  year, program, outcome, scope, near, status,
  sort = 'priority', order = 'asc', limit = 100, offset = 0,
} = {}) {
  const params = new URLSearchParams({ sort, order, limit: String(limit), offset: String(offset) });
  if (year != null) params.set('year', String(year));
  if (program) params.set('program', program);
  if (outcome) params.set('outcome', outcome);
  if (scope) params.set('scope', scope);
  if (near != null) params.set('near', String(near));
  if (status) params.set('status', status);
  return v2Request(`/portfolio${qs(params)}`);
}

/**
 * Why one client is worth calling, ranked by priority band.
 *
 * Deterministic and claims-only — no payroll, no engine — so a per-row button
 * costs a query. This is the same brief `ClientSituationAgent` narrates.
 */
export async function fetchClientSituation(clientId, { year } = {}) {
  const params = new URLSearchParams();
  if (year != null) params.set('year', String(year));
  return v2Request(`/clients/${encodeURIComponent(clientId)}/situation${qs(params)}`);
}

/**
 * WI-21, saved. Records a location's base year (or clears it with null) and
 * starts a recalculation in the background; the grid re-reads when it lands.
 */
export async function saveBaseYear(clientId, unitId, { baseYear, justification = null, state = 'GA' } = {}) {
  return v2Request(
    `/clients/${encodeURIComponent(clientId)}/units/${encodeURIComponent(unitId)}/base-year`,
    jsonPost({ base_year: baseYear ?? null, justification, state }),
  );
}

/**
 * WI-21. One location re-priced against a base year the reader chose. A read of
 * the run's own averages: nothing saved, and the certified figures unchanged.
 */
export async function fetchUnitRebase(clientId, unitId, { baseYear, method = 'min_max', state = 'GA' } = {}) {
  const params = new URLSearchParams({ base_year: String(baseYear), method, state });
  return v2Request(`/clients/${encodeURIComponent(clientId)}/units/${encodeURIComponent(unitId)}/rebase${qs(params)}`);
}

/** Every location for one client, read from `unit_year_master`. */
export async function fetchClientUnits(clientId, {
  year, state, method = 'min_max', limit = 200, offset = 0,
} = {}) {
  const params = new URLSearchParams({ method, limit: String(limit), offset: String(offset) });
  if (year != null) params.set('year', String(year));
  if (state) params.set('state', state);
  return v2Request(`/clients/${encodeURIComponent(clientId)}/units${qs(params)}`);
}

/**
 * One location's employees for a year, NARROWED to a month when given.
 *
 * `month` filters rather than annotates: the drawer's count is the number of
 * people who actually contributed to that month.
 *
 * `sort` and `filter` are SERVER-SIDE. Candle Bottle has 10,236 employees
 * across 101 units, so the alternative is fetching them all to throw most away.
 * The two cohorts filter independently — narrowing the counted list must not
 * move the near-miss count sitting behind a tab.
 */
export async function fetchClientUnit(clientId, unitId, {
  year, month, state, method = 'min_max',
  sort, order, filter, nearFilter, nearMinHours,
} = {}) {
  const params = new URLSearchParams({ method });
  if (year != null) params.set('year', String(year));
  if (month != null) params.set('month', String(month));
  if (state) params.set('state', state);
  if (sort) params.set('sort', sort);
  if (order) params.set('order', order);
  if (filter) params.set('filter', filter);
  if (nearFilter) params.set('near_filter', nearFilter);
  if (nearMinHours != null) params.set('near_min_hours', String(nearMinHours));
  return v2Request(
    `/clients/${encodeURIComponent(clientId)}/units/${encodeURIComponent(unitId)}${qs(params)}`,
  );
}

/**
 * One employee's derivation, keyed by the opaque handle.
 *
 * `record_token` is a SHA-256 of (client, programme, year, employee) — safe in a
 * URL precisely because it cannot be reversed. The employee id it stands for
 * must never take its place here.
 */
export async function fetchEmployeeV2(recordToken, { clientId, year, state, method = 'min_max' } = {}) {
  const params = new URLSearchParams({ method });
  if (clientId != null && clientId !== 'portfolio') params.set('client_id', String(clientId));
  if (year != null) params.set('year', String(year));
  if (state) params.set('state', state);
  return v2Request(`/employees/${encodeURIComponent(recordToken)}${qs(params)}`);
}

/** Trigger a calculation for one client-year. Per client by design — no sweep. */
export async function runClientCalculation(clientId, { year, state = 'GA', triggeredBy } = {}) {
  return v2Request(`/clients/${encodeURIComponent(clientId)}/runs`, jsonPost({
    year: Number(year),
    state,
    ...(triggeredBy ? { triggered_by: triggeredBy } : {}),
  }));
}

/** The live run for a client, or null when it has never been calculated. */
export async function fetchLatestRun(clientId) {
  const r = await fetch(`${BASE}/api/v2/clients/${encodeURIComponent(clientId)}/runs/latest`);
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`latest run ${r.status}`);
  return r.json();
}

// --- Scope: the persistent client x program x year dimension (B3) ----------

export async function fetchScope() {
  const r = await fetch(`${BASE}/api/scope`);
  if (!r.ok) throw new Error(`scope ${r.status}`);
  return r.json();
}

export async function fetchClientScope(accountId) {
  const r = await fetch(`${BASE}/api/scope/client/${encodeURIComponent(accountId)}`);
  if (!r.ok) {
    let detail = '';
    try { detail = (await r.json())?.detail || ''; } catch { /* non-JSON error */ }
    throw new Error(`client scope ${r.status}${detail ? ` · ${detail}` : ''}`);
  }
  return r.json();
}

// --- Claims: program coverage, the variance grid B4 renders ----------------

async function claimsRequest(path, options = {}) {
  const r = await fetch(`${BASE}/api/claims${path}`, options);
  if (!r.ok) {
    let detail = '';
    try { detail = (await r.json())?.detail || ''; } catch { /* non-JSON error */ }
    throw new Error(`claims ${r.status}${detail ? ` · ${detail}` : ''}`);
  }
  return r.json();
}

export const fetchPortfolioCoverage = (taxYear) =>
  claimsRequest(taxYear ? `/coverage?tax_year=${encodeURIComponent(taxYear)}` : '/coverage');

export const fetchClientCoverage = (clientId, { programCode, taxYear, taxYears } = {}) => {
  const params = new URLSearchParams();
  if (programCode) params.set('program_code', programCode);
  if (taxYear) params.set('tax_year', taxYear);
  (taxYears || []).forEach((y) => params.append('tax_years', y));
  const query = params.toString();
  return claimsRequest(`/coverage/${encodeURIComponent(clientId)}${query ? `?${query}` : ''}`);
};

export const fetchClaimCell = (clientId, programCode, taxYear) =>
  claimsRequest(`/cell/${encodeURIComponent(clientId)}/${encodeURIComponent(programCode)}/${encodeURIComponent(taxYear)}`);

export const assessClient = (clientId, body = {}) =>
  claimsRequest('/assess', jsonPost({ client_id: clientId, ...body }));

export const fetchClaimLifecycle = () => claimsRequest('/lifecycle');

/**
 * In-year progress for one client-state-year — the "how am I doing" check.
 *
 * Separate from `fetchForecast` because it answers a different question: the
 * forecast projects credit across states, this one answers *is this client on
 * track and who would move the needle*, and carries the near-the-line cohort
 * with it so the two halves cannot disagree.
 */
export async function fetchInYearProgress({ taxYear, state, asOf, accountId, within } = {}) {
  const params = new URLSearchParams({ state });
  if (asOf) params.set('as_of', asOf);
  if (within != null) params.set('within', String(within));
  withAccount(params, accountId);
  const r = await fetch(`${BASE}/api/progress/${encodeURIComponent(taxYear)}?${params}`);
  if (!r.ok) {
    let detail = '';
    try { detail = (await r.json())?.detail || ''; } catch { /* non-JSON error */ }
    throw new Error(detail || `Progress request failed (${r.status})`);
  }
  return r.json();
}

/**
 * Employee-level threshold proximity — who is near the hours/wage line.
 *
 * Named apart from `fetchProximity` deliberately: that one is CLIENT-grain
 * (which accounts are near a jobs threshold, `/api/claims/proximity`), this one
 * is EMPLOYEE-grain (`/api/proximity/{year}`). Two things called "proximity" at
 * different grains is how the wrong number reaches a screen.
 */
export async function fetchEmployeeProximity({
  taxYear, state, method = 'min_max', within = 5, limit = 100, accountId, restOfYear = false,
} = {}) {
  const params = new URLSearchParams({
    state, method, within: String(within), limit: String(limit),
  });
  withAccount(params, accountId);
  // WI-19: what each row needs over the rest of the year, as of the checkpoint.
  if (restOfYear) params.set('rest_of_year', 'true');
  const r = await fetch(`${BASE}/api/proximity/${encodeURIComponent(taxYear)}?${params}`);
  if (!r.ok) {
    let detail = '';
    try { detail = (await r.json())?.detail || ''; } catch { /* non-JSON error */ }
    throw new Error(detail || `Proximity request failed (${r.status})`);
  }
  return r.json();
}

export async function simulateOneZero(payload) {
  const r = await fetch(`${BASE}/api/simulate/onezero`, jsonPost(payload));
  if (!r.ok) {
    let detail = '';
    try { detail = (await r.json())?.detail || ''; } catch { /* non-JSON error */ }
    throw new Error(`simulate ${r.status}${detail ? ` · ${detail}` : ''}`);
  }
  return r.json();
}

/**
 * What-if for a STACK of employees, each working more hours a week and/or at
 * a raise for the rest of the year, projected together in one engine run.
 * Carries record tokens, never employee ids.
 */
export async function simulateEmployees({ clientId, taxYear, state = 'GA', method = 'min_max', employees = [] }) {
  const r = await fetch(`${BASE}/api/simulate/employee`, jsonPost({
    client_id: clientId, tax_year: taxYear, state, method,
    employees: employees.map((e) => ({
      record_token: e.recordToken,
      additional_weekly_hours: Number(e.additionalWeeklyHours) || 0,
      hourly_raise: Number(e.hourlyRaise) || 0,
    })),
  }));
  if (!r.ok) {
    let detail = '';
    try { detail = (await r.json())?.detail || ''; } catch { /* non-JSON error */ }
    throw new Error(`simulate ${r.status}${detail ? ` · ${detail}` : ''}`);
  }
  return r.json();
}

/**
 * What-if at ONE location, priced the way the location grid prices it: against
 * that location's own frozen base year. A 404 carries the reason — a base year,
 * a location the run does not hold, or payroll that has moved since the run.
 */
export async function simulateUnit({
  clientId, worksiteId, taxYear, state = 'GA', method = 'min_max', action, magnitude,
  hireWeeklyHours = null, hireHourlyRate = null,
}) {
  const r = await fetch(`${BASE}/api/simulate/unit`, jsonPost({
    client_id: clientId, worksite_id: worksiteId, tax_year: taxYear,
    state, method, action, magnitude,
    // WI-22. What a hired role is; omitted, a full-time role clear of both floors.
    ...(hireWeeklyHours != null ? { hire_weekly_hours: hireWeeklyHours } : {}),
    ...(hireHourlyRate != null ? { hire_hourly_rate: hireHourlyRate } : {}),
  }));
  if (!r.ok) {
    let detail = '';
    try { detail = (await r.json())?.detail || ''; } catch { /* non-JSON error */ }
    throw new Error(`simulate ${r.status}${detail ? ` · ${detail}` : ''}`);
  }
  return r.json();
}

// --- Who the API believes the caller is ------------------------------------

/**
 * The signed-in identity, as the API validated it. A decision is attributed
 * from this, never from a name hard-coded in the browser. Under AUTH_MODE=none
 * the answer is `authenticated: false` with no UPN, and the server attributes
 * the write itself.
 */
export async function fetchMe() {
  const r = await fetch(`${BASE}/api/me`);
  if (!r.ok) throw new Error(`me ${r.status}`);
  return r.json();
}

// --- Claim packages: generated server-side, downloaded through the API -----

/**
 * Build one client-year's claim package (XLSX). Resolves to the artifact,
 * including its `artifact_id`. A 409 means the client has never been
 * calculated, which is a state to say, not an empty file to hand over.
 */
export async function createClaimPackage(clientId, taxYear) {
  const r = await fetch(
    `${BASE}/api/clients/${encodeURIComponent(clientId)}/packages?tax_year=${encodeURIComponent(taxYear)}`,
    { method: 'POST' },
  );
  if (!r.ok) {
    let detail = '';
    try { detail = (await r.json())?.detail || ''; } catch { /* non-JSON error */ }
    throw new Error(`package ${r.status}${detail ? ` · ${detail}` : ''}`);
  }
  return r.json();
}

/**
 * The artifact's bytes, streamed by the API (no storage URL ever reaches the
 * browser). Resolves to `{ blob, fileName }`.
 */
export async function downloadArtifact(clientId, artifactId) {
  const r = await fetch(
    `${BASE}/api/clients/${encodeURIComponent(clientId)}/artifacts/${encodeURIComponent(artifactId)}`,
  );
  if (!r.ok) throw new Error(`artifact ${r.status}`);
  const disposition = r.headers?.get?.('content-disposition') || '';
  const fileName = /filename="([^"]+)"/.exec(disposition)?.[1] || `${artifactId}.xlsx`;
  return { blob: await r.blob(), fileName };
}

// --- Agent findings: what an agent noticed, and what a human decided --------

async function findingsRequest(path, options = {}) {
  const r = await fetch(`${BASE}/api/findings${path}`, options);
  if (!r.ok) {
    let detail = '';
    try { detail = (await r.json())?.detail || ''; } catch { /* non-JSON error */ }
    throw new Error(`findings ${r.status}${detail ? ` · ${detail}` : ''}`);
  }
  return r.json();
}

export const fetchFindings = (clientId, taxYear, state) =>
  findingsRequest(
    `/${encodeURIComponent(clientId)}/${encodeURIComponent(taxYear)}${state ? `?state=${encodeURIComponent(state)}` : ''}`,
  );

export const resolveFinding = (findingId, body) =>
  findingsRequest(`/${encodeURIComponent(findingId)}/resolve`, jsonPost(body));

export const reopenFinding = (findingId, body) =>
  findingsRequest(`/${encodeURIComponent(findingId)}/reopen`, jsonPost(body));

export async function fetchRules() {
  const r = await fetch(`${BASE}/api/rules`);
  if (!r.ok) throw new Error(`rules ${r.status}`);
  return r.json();
}

export async function verifyRulePack(code, payload) {
  const r = await fetch(`${BASE}/api/rules/${encodeURIComponent(code)}/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(`rule verify ${r.status}`);
  return r.json();
}

export async function fetchOneZero(taxYear, state, opts = {}) {
  // [H5][I1][H4] optional method ('pay_period'|'min_max'|'both') + fein scope.
  const params = new URLSearchParams();
  if (state) params.set('state', state);
  if (opts.method) params.set('method', opts.method);
  if (opts.fein) params.set('fein', opts.fein);
  withAccount(params, opts.accountId);
  const r = await fetch(`${BASE}/api/onezero/${taxYear}${qs(params)}`);
  if (!r.ok) throw new Error(`onezero ${r.status}`);
  return r.json();
}

export async function fetchMonthlyAlerts(taxYear, state, accountId) {
  // [J3] UX-03 — monthly credit-tracking alerts + per-employee levers.
  const params = new URLSearchParams();
  if (state) params.set('state', state);
  withAccount(params, accountId);
  const r = await fetch(`${BASE}/api/alerts/monthly/${taxYear}${qs(params)}`);
  if (!r.ok) throw new Error(`monthly alerts ${r.status}`);
  return r.json();
}

export async function runOneZeroSimulation(payload) {
  // [J2] UX-02 — entity-level what-if against the statutory One/Zero engine.
  const r = await fetch(`${BASE}/api/simulate/onezero`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(`onezero simulate ${r.status}`);
  return r.json();
}

export async function fetchRetroactiveScan(accountId) {
  const params = withAccount(new URLSearchParams(), accountId);
  const r = await fetch(`${BASE}/api/onezero/retroactive/scan${qs(params)}`);
  if (!r.ok) throw new Error(`retroactive ${r.status}`);
  return r.json();
}

export async function fetchPerformance(taxYear, state, worksite, accountId) {
  const params = new URLSearchParams();
  if (state) params.set('state', state);
  if (worksite) params.set('worksite', worksite);  // [O1] UX-05 field-level scope
  withAccount(params, accountId);
  const r = await fetch(`${BASE}/api/performance/${taxYear}${qs(params)}`);
  if (!r.ok) throw new Error(`performance ${r.status}`);
  return r.json();
}

// [N2] FCST-01 — "how am I doing" run-rate forecast toward the finish line.
export async function fetchForecast(taxYear, state, asOf, accountId) {
  const params = new URLSearchParams();
  if (state) params.set('state', state);
  if (asOf) params.set('as_of', asOf);
  withAccount(params, accountId);
  const r = await fetch(`${BASE}/api/forecast/${taxYear}${qs(params)}`);
  if (!r.ok) throw new Error(`forecast ${r.status}`);
  return r.json();
}

// [L2] CALC-08 — designation timelines + parallel-calc flags for a state.
export async function fetchDesignations(state, taxYear = 2025) {
  const r = await fetch(`${BASE}/api/designations/${encodeURIComponent(state)}?tax_year=${taxYear}`);
  if (!r.ok) throw new Error(`designations ${r.status}`);
  return r.json();
}

// Stage 1 — Data Ingestion: source → canonical → QC exception report.
export async function fetchIngestion(taxYear, state = 'GA', accountId) {
  const year = requireYear(taxYear, 'ingestion');
  const params = new URLSearchParams({ state });
  withAccount(params, accountId);
  const r = await fetch(`${BASE}/api/ingestion/${year}${qs(params)}`);
  if (!r.ok) throw new Error(`ingestion ${r.status}`);
  return r.json();
}

export async function resolveException(taxYear, exceptionId, payload) {
  const r = await fetch(
    `${BASE}/api/ingestion/${taxYear}/exceptions/${encodeURIComponent(exceptionId)}/resolve`,
    { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) },
  );
  if (!r.ok) throw new Error(`resolve exception ${r.status}`);
  return r.json();
}

// Full source browser — paged + searchable, read-only.
export async function fetchIngestionRows(taxYear, {
  q = '', limit = 25, offset = 0, state = 'GA', accountId, sort, order,
} = {}) {
  const year = requireYear(taxYear, 'ingestion rows');
  const params = new URLSearchParams({ state, q, limit: String(limit), offset: String(offset) });
  withAccount(params, accountId);
  // Sorted by the server before paging; see `ingestion_rows`.
  if (sort) params.set('sort', sort);
  if (order) params.set('order', order);
  const r = await fetch(`${BASE}/api/ingestion/${year}/rows?${params.toString()}`);
  if (!r.ok) throw new Error(`ingestion rows ${r.status}`);
  return r.json();
}

// Stage 2's per-employee drill used to live here as
// `fetchEmployeeDrill(taxYear, employeeId, ...)` and
// `reviewEmployee(employeeId, ...)`, both of which put the EMPLOYEE ID in the
// URL path. An id in a path reaches the browser history, the proxy log and the
// access log, none of which are places payroll identity may go. Neither had a
// caller outside this module's own tests.
//
// The drill is `fetchEmployeeV2` / `fetchClientEmployeeDrill` above, keyed by
// `record_token`. The review annotation has no replacement yet: its backend
// route still takes the id in the path, so a token-keyed version needs that
// route changed first.

// [P1] PILOT-04 — reconcile live engine output against the benchmark fixture.
export async function fetchReconcile(taxYear, accountId) {
  const params = withAccount(new URLSearchParams(), accountId);
  const r = await fetch(`${BASE}/api/reconcile/${taxYear}${qs(params)}`);
  if (!r.ok) throw new Error(`reconcile ${r.status}`);
  return r.json();
}

export async function fetchTriggers(accountId) {
  const params = withAccount(new URLSearchParams(), accountId);
  const r = await fetch(`${BASE}/api/triggers${qs(params)}`);
  if (!r.ok) throw new Error(`triggers ${r.status}`);
  return r.json();
}

export async function fetchHealth() {
  const r = await fetch(`${BASE}/api/health`);
  if (!r.ok) throw new Error(`health ${r.status}`);
  return r.json();
}

/**
 * Stream the chat response as SSE.
 * Calls onEvent({event, data}) for each parsed event; resolves when the stream ends.
 */
export async function streamChat(message, onEvent, signal, scope = {}, history = [], { confirmed = false } = {}) {
  const payload = {
    message,
    ...(history.length ? { history } : {}),
    ...(scope.state ? { state: scope.state } : {}),
    ...(scope.clientId != null && scope.clientId !== 'portfolio' ? { client_id: Number(scope.clientId) } : {}),
    ...(scope.taxYear != null ? { tax_year: Number(scope.taxYear) } : {}),
    ...(scope.method ? { method: scope.method } : {}),
    // The reader picked this client from a clarifying question; do not ask again.
    ...(confirmed ? { client_confirmed: true } : {}),
  };

  const r = await fetch(`${BASE}/api/chat`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', accept: 'text/event-stream' },
    body: JSON.stringify(payload),
    signal,
  });
  if (!r.ok || !r.body) throw new Error(`chat ${r.status}`);
  await readSse(r, onEvent);
}

/**
 * The Copilot summary for one page (29 Sep). Streams the same SSE shape as
 * chat — `brief`, `token`, then `check` (or `fallback` when Copilot is not
 * connected) — so the panel can say whether every figure it states is one the
 * page's own data holds. Carries a record token for the employee page, never
 * an employee id.
 */
export async function streamPageSummary(request, onEvent, signal) {
  const body = {
    page: request.page,
    ...(request.clientId != null && request.clientId !== 'portfolio' ? { client_id: Number(request.clientId) } : {}),
    ...(request.taxYear != null ? { tax_year: Number(request.taxYear) } : {}),
    ...(request.state ? { state: request.state } : {}),
    ...(request.method ? { method: request.method } : {}),
    ...(request.worksiteId ? { worksite_id: request.worksiteId } : {}),
    ...(request.month != null ? { month: Number(request.month) } : {}),
    ...(request.recordToken ? { record_token: request.recordToken } : {}),
  };
  const r = await fetch(`${BASE}/api/summary`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', accept: 'text/event-stream' },
    body: JSON.stringify(body),
    signal,
  });
  if (!r.ok || !r.body) throw new Error(`summary ${r.status}`);
  await readSse(r, onEvent);
}

async function readSse(r, onEvent) {

  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';

  // SSE frames are separated by a blank line.
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });

    let idx;
    while ((idx = buf.indexOf('\n\n')) !== -1) {
      const frame = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      const ev = parseFrame(frame);
      if (ev) onEvent(ev);
    }
  }
}

function parseFrame(frame) {
  let event = 'message';
  const dataLines = [];
  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return null;
  let data;
  try { data = JSON.parse(dataLines.join('\n')); } catch { data = { raw: dataLines.join('\n') }; }
  return { event, data };
}
