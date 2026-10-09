// Smoke tests for the api.js fetch wrappers. Verifies:
// - Each helper hits the documented URL
// - Each helper resolves on 200 and throws on non-2xx
// - Mutating helpers send the expected method + JSON body
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import {
  fetchRules,
  fetchOneZero,
  fetchPerformance,
  fetchTriggers,
  fetchRetroactiveScan,
  fetchForecast,
  fetchDesignations,
  fetchReconcile,
  fetchMonthlyAlerts,
  runOneZeroSimulation,
  simulateUnit,
  fetchUnitRebase,
  saveBaseYear,
  simulateEmployees,
  streamPageSummary,
  fetchEmployeeProximity,
  verifyRulePack,
  fetchIngestion,
  resolveException,
  fetchIngestionRows,
  fetchWorkspace,
  refreshWorkspace,
  searchWorkspaceSource,
  searchWorkspaceEligibility,
  fetchWorkspaceEmployee,
  fetchWorkspaceOneZero,
  fetchWorkspaceContributors,
  fetchWorkspaceCalculationWalk,
  fetchWorkspaceAssumptions,
  fetchWorkspaceComparison,
  fetchWorkspaceComparisonStage,
  fetchEligibility,
  fetchOneZeroMatrix,
  fetchClientEmployeeDrill,
  fetchMe,
  createClaimPackage,
  downloadArtifact,
} from './api.js';

function ok(body = {}) {
  return { ok: true, status: 200, json: async () => body };
}

function err(status = 500) {
  return { ok: false, status, json: async () => ({}) };
}

let fetchMock;

beforeEach(() => {
  fetchMock = vi.fn();
  globalThis.fetch = fetchMock;
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('v2 — the warehouse-backed read surface', () => {
  it('fetchPortfolioV2 hits /api/v2/portfolio', async () => {
    const { fetchPortfolioV2 } = await import('./api.js');
    fetchMock.mockResolvedValueOnce(ok({ items: [] }));
    await fetchPortfolioV2({ year: 2023, sort: 'jobs_gap', order: 'asc', limit: 100 });
    expect(fetchMock.mock.calls[0][0]).toBe(
      '/api/v2/portfolio?sort=jobs_gap&order=asc&limit=100&offset=0&year=2023',
    );
  });

  it('fetchClientUnits hits /api/v2/clients/{id}/units', async () => {
    const { fetchClientUnits } = await import('./api.js');
    fetchMock.mockResolvedValueOnce(ok({ items: [] }));
    await fetchClientUnits(1001, { year: 2023, method: 'min_max', limit: 200 });
    expect(fetchMock.mock.calls[0][0]).toBe(
      '/api/v2/clients/1001/units?method=min_max&limit=200&offset=0&year=2023',
    );
  });

  it('fetchClientUnit narrows to a month when one is given', async () => {
    const { fetchClientUnit } = await import('./api.js');
    fetchMock.mockResolvedValueOnce(ok({ employees: [] }));
    await fetchClientUnit(1001, 'GA_1134481', { year: 2023, month: 5 });
    expect(fetchMock.mock.calls[0][0]).toBe(
      '/api/v2/clients/1001/units/GA_1134481?method=min_max&year=2023&month=5',
    );
  });

  it('fetchEmployeeV2 keys on the opaque token, never an employee id', async () => {
    const { fetchEmployeeV2 } = await import('./api.js');
    fetchMock.mockResolvedValueOnce(ok({}));
    await fetchEmployeeV2('cecdd3826720321b2f00c5a0', { clientId: 1001, year: 2023 });
    const [url] = fetchMock.mock.calls[0];
    expect(url).toBe(
      '/api/v2/employees/cecdd3826720321b2f00c5a0?method=min_max&client_id=1001&year=2023',
    );
    expect(url).not.toMatch(/E\d{5}/);
  });

  it('runClientCalculation posts the year and state', async () => {
    const { runClientCalculation } = await import('./api.js');
    fetchMock.mockResolvedValueOnce(ok({ run_id: 'abc' }));
    await runClientCalculation(1001, { year: 2023, state: 'GA' });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/v2/clients/1001/runs');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ year: 2023, state: 'GA' });
  });

  it('fetchLatestRun returns null for a client that has never been calculated', async () => {
    const { fetchLatestRun } = await import('./api.js');
    fetchMock.mockResolvedValueOnce({ ok: false, status: 404, json: async () => ({}) });
    await expect(fetchLatestRun(2002)).resolves.toBeNull();
  });

  it('isCalculated separates "no run" from "a run that found zero"', async () => {
    const { isCalculated } = await import('./api.js');
    // Both have no items. Only one of them is a figure.
    expect(isCalculated({ calculation_state: 'not_calculated', run: null, items: [] })).toBe(false);
    expect(isCalculated({ calculation_state: 'calculated', run: { run_id: 'r' }, items: [] })).toBe(true);
  });
});

describe('Reference Dataset Client workspace helpers', () => {
  it.each([
    [fetchWorkspace, '/api/workspace'],
    [fetchWorkspaceCalculationWalk, '/api/workspace/calculation-walk'],
    [fetchWorkspaceAssumptions, '/api/workspace/assumptions'],
    [fetchWorkspaceComparison, '/api/workspace/comparison'],
  ])('%o → %s', async (fn, url) => {
    fetchMock.mockResolvedValueOnce(ok({ grounded: true }));
    await fn();
    expect(fetchMock).toHaveBeenLastCalledWith(url, {});
  });

  it('refreshWorkspace posts without private values', async () => {
    fetchMock.mockResolvedValueOnce(ok());
    await refreshWorkspace();
    expect(fetchMock).toHaveBeenLastCalledWith('/api/workspace/refresh', { method: 'POST' });
  });

  it.each([
    [searchWorkspaceSource, '/api/workspace/source/search', { q: 'employee', limit: 25 }],
    [searchWorkspaceEligibility, '/api/workspace/eligibility/search', { status: 'both' }],
    [fetchWorkspaceContributors, '/api/workspace/onezero/contributors', { method: 'min_max', unit_id: 'U1', fein: 'F1', month_index: 0 }],
  ])('%o posts JSON to %s', async (fn, url, payload) => {
    fetchMock.mockResolvedValueOnce(ok());
    await fn(payload);
    expect(fetchMock).toHaveBeenLastCalledWith(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  });

  it('employee drill sends only the opaque record token', async () => {
    fetchMock.mockResolvedValueOnce(ok());
    await fetchWorkspaceEmployee('opaque-token');
    expect(fetchMock).toHaveBeenLastCalledWith('/api/workspace/employee', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ record_token: 'opaque-token' }),
    });
  });

  it('method and comparison stage URLs are encoded', async () => {
    fetchMock.mockResolvedValue(ok());
    await fetchWorkspaceOneZero('min_max');
    expect(fetchMock).toHaveBeenLastCalledWith('/api/workspace/onezero/min_max', {});
    await fetchWorkspaceComparisonStage('common_employee_totals');
    expect(fetchMock).toHaveBeenLastCalledWith('/api/workspace/comparison/stage', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stage: 'common_employee_totals' }),
    });
  });

  it('the per-client reads carry the scope and omit empty filters', async () => {
    fetchMock.mockResolvedValue(ok());
    await fetchEligibility(2023, { state: 'GA', accountId: 1001, limit: 25, offset: 50 });
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/eligibility/2023?state=GA&status=all&limit=25&offset=50&account_id=1001',
    );

    // near_floor and q are only sent when set, so a default read stays clean.
    await fetchEligibility(2023, { accountId: 2003, nearFloor: true, q: 'E12' });
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/eligibility/2023?state=GA&status=all&limit=50&offset=0&account_id=2003&near_floor=true&q=E12',
    );

    await fetchOneZeroMatrix(2023, { accountId: 1001, method: 'pay_period' });
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/onezero/matrix/2023?state=GA&method=pay_period&account_id=1001',
    );
  });

  it('a declined client-year rejects rather than resolving empty', async () => {
    // A 404 here means "no statute for that year" — surfacing it as an empty
    // population would read as "nobody qualifies".
    fetchMock.mockResolvedValue({ ok: false, status: 404, json: async () => ({}) });
    await expect(fetchEligibility(2015, { accountId: 1001 })).rejects.toThrow('eligibility 404');
    await expect(fetchOneZeroMatrix(2015, { accountId: 1001 })).rejects.toThrow('onezero matrix 404');
  });
});

describe('GET helpers hit the right URL', () => {
  it.each([
    [fetchRules, '/api/rules'],
    [fetchTriggers, '/api/triggers'],
    [fetchRetroactiveScan, '/api/onezero/retroactive/scan'],
    [fetchMe, '/api/me'],
  ])('%o → %s', async (fn, url) => {
    fetchMock.mockResolvedValueOnce(ok({ x: 1 }));
    const result = await fn();
    expect(result).toEqual({ x: 1 });
    expect(fetchMock).toHaveBeenCalledWith(url);
  });
});

describe('fetchMe — the signed-in identity (AUTH-4)', () => {
  it('returns what the API validated', async () => {
    fetchMock.mockResolvedValueOnce(ok({ auth_mode: 'entra', authenticated: true, upn: 'analyst@example.com' }));
    await expect(fetchMe()).resolves.toMatchObject({ upn: 'analyst@example.com' });
  });

  it('throws on 401 rather than inventing an identity', async () => {
    fetchMock.mockResolvedValueOnce(err(401));
    await expect(fetchMe()).rejects.toThrow('me 401');
  });
});

describe('claim packages (BLOB-4)', () => {
  it('createClaimPackage POSTs the client-year and returns the artifact', async () => {
    fetchMock.mockResolvedValueOnce(ok({ artifact_id: 'a1' }));
    await expect(createClaimPackage(1001, 2024)).resolves.toEqual({ artifact_id: 'a1' });
    expect(fetchMock).toHaveBeenCalledWith('/api/clients/1001/packages?tax_year=2024', { method: 'POST' });
  });

  it('createClaimPackage surfaces the 409 detail', async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, status: 409, json: async () => ({ detail: 'never calculated' }) });
    await expect(createClaimPackage(1001, 2024)).rejects.toThrow('package 409 · never calculated');
  });

  it('downloadArtifact streams the bytes from the API with the served file name', async () => {
    const blob = new Blob(['xlsx']);
    fetchMock.mockResolvedValueOnce({
      ok: true, status: 200, blob: async () => blob,
      headers: { get: (h) => (h === 'content-disposition' ? 'attachment; filename="pkg.xlsx"' : null) },
    });
    await expect(downloadArtifact(1001, 'a1')).resolves.toEqual({ blob, fileName: 'pkg.xlsx' });
    expect(fetchMock).toHaveBeenCalledWith('/api/clients/1001/artifacts/a1');
  });

  it('downloadArtifact throws on a denied download', async () => {
    fetchMock.mockResolvedValueOnce(err(403));
    await expect(downloadArtifact(1001, 'a1')).rejects.toThrow('artifact 403');
  });
});

describe('parameterized GETs', () => {
  it('fetchOneZero passes tax year and optional state', async () => {
    fetchMock.mockResolvedValueOnce(ok({ tax_year: 2025 }));
    await fetchOneZero(2025);
    expect(fetchMock).toHaveBeenCalledWith('/api/onezero/2025');

    fetchMock.mockResolvedValueOnce(ok({ tax_year: 2025 }));
    await fetchOneZero(2025, 'GA');
    expect(fetchMock).toHaveBeenLastCalledWith('/api/onezero/2025?state=GA');
  });

  it('fetchPerformance passes tax year and optional state', async () => {
    fetchMock.mockResolvedValueOnce(ok({}));
    await fetchPerformance(2025, 'GA');
    expect(fetchMock).toHaveBeenLastCalledWith('/api/performance/2025?state=GA');
  });

  it('[H5][I1] fetchOneZero appends method + fein query params', async () => {
    fetchMock.mockResolvedValueOnce(ok({}));
    await fetchOneZero(2025, 'GA', { method: 'min_max', fein: '58-1' });
    expect(fetchMock).toHaveBeenLastCalledWith('/api/onezero/2025?state=GA&method=min_max&fein=58-1');
  });

  it('[J3] fetchMonthlyAlerts passes tax year and optional state', async () => {
    fetchMock.mockResolvedValueOnce(ok({}));
    await fetchMonthlyAlerts(2025, 'SC');
    expect(fetchMock).toHaveBeenLastCalledWith('/api/alerts/monthly/2025?state=SC');
  });

  it('[N2] fetchForecast passes tax year, state and as_of', async () => {
    fetchMock.mockResolvedValueOnce(ok({}));
    await fetchForecast(2025, 'GA', '2025-08-31');
    expect(fetchMock).toHaveBeenLastCalledWith('/api/forecast/2025?state=GA&as_of=2025-08-31');
  });

  it('[L2] fetchDesignations hits the state designations URL', async () => {
    fetchMock.mockResolvedValueOnce(ok({}));
    await fetchDesignations('GA', 2025);
    expect(fetchMock).toHaveBeenLastCalledWith('/api/designations/GA?tax_year=2025');
  });

  it('Stage1 fetchIngestion hits the ingestion URL with state', async () => {
    fetchMock.mockResolvedValueOnce(ok({}));
    await fetchIngestion(2025, 'GA');
    expect(fetchMock).toHaveBeenLastCalledWith('/api/ingestion/2025?state=GA');
  });

  describe('a year-scoped endpoint refuses an absent year instead of sending "null"', () => {
    // The scope reports `year: null` until a client's payroll resolves. A JS
    // default parameter does not cover `null`, so every component's declared
    // fallback was dead and the request went out as `/api/ingestion/null` —
    // a 422, re-fired on every render. One client logged 4,968 console errors
    // before the page settled.
    //
    // The year is a PATH segment, so an absent one is not a missing filter:
    // it is a different, wrong URL. These assert that no request is made.
    it.each([
      ['fetchIngestion', () => fetchIngestion(null, 'GA')],
      ['fetchIngestionRows', () => fetchIngestionRows(null, { state: 'GA' })],
    ])('%s throws rather than requesting', async (_name, call) => {
      await expect(call()).rejects.toThrow(/needs a tax year/);
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it('accepts a numeric string, because a URL param arrives as one', async () => {
      fetchMock.mockResolvedValueOnce(ok({}));
      await fetchIngestion('2024', 'GA');
      expect(fetchMock).toHaveBeenLastCalledWith('/api/ingestion/2024?state=GA');
    });
  });

  it('fetchIngestionRows passes search + paging params', async () => {
    fetchMock.mockResolvedValueOnce(ok({}));
    await fetchIngestionRows(2025, { q: 'E00200', limit: 25, offset: 50, state: 'GA' });
    expect(fetchMock).toHaveBeenLastCalledWith('/api/ingestion/2025/rows?state=GA&q=E00200&limit=25&offset=50');
  });

  it('[P1] fetchReconcile hits the reconcile URL', async () => {
    fetchMock.mockResolvedValueOnce(ok({}));
    await fetchReconcile(2025);
    expect(fetchMock).toHaveBeenLastCalledWith('/api/reconcile/2025');
  });
});

describe('error handling', () => {
  it('throws when a GET returns non-2xx', async () => {
    fetchMock.mockResolvedValueOnce(err(500));
    await expect(fetchRules()).rejects.toThrow(/rules 500/);
  });
});

describe('fetchClientEmployeeDrill', () => {
  it('posts the handle in the body, never in the path', async () => {
    fetchMock.mockResolvedValueOnce(ok({ employee_id: 'E1' }));
    await fetchClientEmployeeDrill({ recordToken: 'abc123def456', taxYear: 2025, accountId: 1001 });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/employee/drill');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({
      record_token: 'abc123def456', tax_year: 2025, state: 'GA', account_id: 1001,
    });
  });

  it('omits the client for portfolio, which is the absence of one', async () => {
    fetchMock.mockResolvedValueOnce(ok({}));
    await fetchClientEmployeeDrill({ recordToken: 'abc123def456', taxYear: 2025, accountId: 'portfolio' });
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).account_id).toBeUndefined();
  });

  it('throws on non-2xx rather than rendering an empty drill', async () => {
    fetchMock.mockResolvedValueOnce(err(404));
    await expect(fetchClientEmployeeDrill({ recordToken: 'abc123def456', taxYear: 2025 }))
      .rejects.toThrow(/employee drill 404/);
  });
});

describe('POST helpers send method + JSON body', () => {
  it('resolveException posts to /api/ingestion/{ty}/exceptions/{id}/resolve', async () => {
    fetchMock.mockResolvedValueOnce(ok({ ok: true }));
    await resolveException(2025, 't2:E1:2025-06', { resolution: 'accept' });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/ingestion/2025/exceptions/t2%3AE1%3A2025-06/resolve');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ resolution: 'accept' });
  });

  it('no wrapper puts an employee id in a URL', async () => {
    // `fetchEmployeeDrill` and `reviewEmployee` did, and neither had a caller.
    // An id in a path reaches browser history, proxy logs and access logs.
    const source = await import('./api.js');
    expect(source.fetchEmployeeDrill).toBeUndefined();
    expect(source.reviewEmployee).toBeUndefined();
  });

  it('[J2] runOneZeroSimulation posts to /api/simulate/onezero', async () => {
    fetchMock.mockResolvedValueOnce(ok({ delta: {} }));
    const payload = { tax_year: 2025, state: 'SC', action: 'adjust_hours', magnitude: 2 };
    await runOneZeroSimulation(payload);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/simulate/onezero');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual(payload);
  });

  it('simulateUnit posts one location to /api/simulate/unit in the wire vocabulary', async () => {
    fetchMock.mockResolvedValueOnce(ok({ delta: {} }));
    await simulateUnit({
      clientId: 2001, worksiteId: 'GA_GA-016', taxYear: 2025, method: 'pay_period',
      action: 'add_headcount', magnitude: 2,
    });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/simulate/unit');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({
      client_id: 2001, worksite_id: 'GA_GA-016', tax_year: 2025, state: 'GA',
      method: 'pay_period', action: 'add_headcount', magnitude: 2,
    });
  });

  it('simulateEmployees posts a stack of record tokens, never employee ids', async () => {
    fetchMock.mockResolvedValueOnce(ok({}));
    await simulateEmployees({
      clientId: 2001, taxYear: 2026,
      employees: [
        { recordToken: 'abc123', additionalWeeklyHours: 2.87 },
        { recordToken: 'def456', additionalWeeklyHours: 0.5, hourlyRaise: 1.25 },
      ],
    });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/simulate/employee');
    expect(JSON.parse(init.body)).toEqual({
      client_id: 2001, tax_year: 2026, state: 'GA', method: 'min_max',
      employees: [
        { record_token: 'abc123', additional_weekly_hours: 2.87, hourly_raise: 0 },
        { record_token: 'def456', additional_weekly_hours: 0.5, hourly_raise: 1.25 },
      ],
    });
  });

  it('fetchEmployeeProximity asks for the rest of the year only when told to', async () => {
    fetchMock.mockResolvedValue(ok({ cohort: [] }));
    await fetchEmployeeProximity({ taxYear: 2025, state: 'GA', accountId: 2001, restOfYear: true });
    expect(fetchMock.mock.calls[0][0]).toContain('rest_of_year=true');
    await fetchEmployeeProximity({ taxYear: 2025, state: 'GA', accountId: 2001 });
    expect(fetchMock.mock.calls[1][0]).not.toContain('rest_of_year');
  });

  it('saveBaseYear posts the choice, and null clears it', async () => {
    fetchMock.mockResolvedValue(ok({ recorded: true }));
    await saveBaseYear(2001, 'GA_GA-010', { baseYear: 2022, justification: 'why' });
    let [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/v2/clients/2001/units/GA_GA-010/base-year');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ base_year: 2022, justification: 'why', state: 'GA' });
    await saveBaseYear(2001, 'GA_GA-010', { baseYear: null });
    [url, init] = fetchMock.mock.calls[1];
    expect(JSON.parse(init.body).base_year).toBeNull();
  });

  it('fetchUnitRebase asks for one location against a chosen base year', async () => {
    fetchMock.mockResolvedValueOnce(ok({ years: [] }));
    await fetchUnitRebase(2001, 'GA_GA-010', { baseYear: 2022, method: 'pay_period' });
    expect(fetchMock.mock.calls[0][0]).toBe(
      '/api/v2/clients/2001/units/GA_GA-010/rebase?base_year=2022&method=pay_period&state=GA',
    );
  });

  it('simulateUnit surfaces the reason a projection was declined', async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, status: 404, json: async () => ({ detail: 'TY2020 is the base year' }) });
    await expect(simulateUnit({ clientId: 2001, worksiteId: 'x', taxYear: 2020, action: 'add_headcount', magnitude: 1 }))
      .rejects.toThrow('TY2020 is the base year');
  });

  it('verifyRulePack URL-encodes the code', async () => {
    fetchMock.mockResolvedValueOnce(ok({}));
    await verifyRulePack('GA JTC', { verified_by: 'Test', note: 'ok' });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/rules/GA%20JTC/verify');
    expect(init.method).toBe('POST');
  });
});


describe('streamChat — the chat wire', () => {
  const sse = (frames) => {
    const bytes = new TextEncoder().encode(frames);
    let done = false;
    return {
      ok: true,
      status: 200,
      body: { getReader: () => ({ read: async () => (done ? { done: true } : ((done = true), { value: bytes, done: false })) }) },
    };
  };

  it('says client_confirmed only when the reader picked the client', async () => {
    const { streamChat } = await import('./api.js');
    fetchMock.mockResolvedValue(sse('event: done\ndata: {}\n\n'));

    await streamChat('what is their trend?', () => {}, undefined, { clientId: 2001, taxYear: 2025 }, [], { confirmed: true });
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({
      message: 'what is their trend?', client_id: 2001, tax_year: 2025, client_confirmed: true,
    });

    await streamChat('hello', () => {}, undefined, {});
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).not.toHaveProperty('client_confirmed');
  });

  it('delivers a clarify frame like any other event', async () => {
    const { streamChat } = await import('./api.js');
    fetchMock.mockResolvedValue(sse('event: clarify\ndata: {"choices":[{"client_id":2001}]}\n\n'));
    const events = [];
    await streamChat('x', (ev) => events.push(ev));
    expect(events).toEqual([{ event: 'clarify', data: { choices: [{ client_id: 2001 }] } }]);
  });
});

describe('the page summary stream (29 Sep)', () => {
  it('posts the page scope with a record token, never an employee id', async () => {
    const encoder = new TextEncoder();
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('event: token\ndata: {"content":"Hi"}\n\n'));
        controller.close();
      },
    });
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, body });
    const events = [];
    await streamPageSummary({
      page: 'employee', clientId: 2001, taxYear: 2026, state: 'GA', recordToken: 'abcdef123456',
    }, (e) => events.push(e));
    const [url, init] = globalThis.fetch.mock.calls[0];
    expect(url).toBe('/api/summary');
    expect(JSON.parse(init.body)).toEqual({
      page: 'employee', client_id: 2001, tax_year: 2026, state: 'GA', record_token: 'abcdef123456',
    });
    expect(events).toEqual([{ event: 'token', data: { content: 'Hi' } }]);
  });

  it('never sends a portfolio scope as a client id', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, body: new ReadableStream({ start: (c) => c.close() }) });
    await streamPageSummary({ page: 'portfolio', clientId: 'portfolio' }, () => {});
    expect(JSON.parse(globalThis.fetch.mock.calls[0][1].body)).toEqual({ page: 'portfolio' });
  });
});

describe('server-side sort (29 Sep)', () => {
  it('asks the eligibility and source-row reads to order before paging', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    await fetchEligibility(2023, { accountId: 1001, sort: 'total_hours', order: 'desc' });
    expect(globalThis.fetch.mock.calls[0][0]).toContain('sort=total_hours');
    expect(globalThis.fetch.mock.calls[0][0]).toContain('order=desc');
    await fetchIngestionRows(2025, { sort: 'hours', order: 'asc' });
    expect(globalThis.fetch.mock.calls[1][0]).toContain('sort=hours');
    await fetchEligibility(2023, { accountId: 1001 });
    expect(globalThis.fetch.mock.calls[2][0]).not.toContain('sort=');
  });
});
