/**
 * The shell: scope is a dimension, not a view.
 *
 * B3's whole claim is that scope PERSISTS — moving from Position to Eligibility
 * must not reset which client you are looking at, because scope is a property
 * of the session rather than of a page. Nothing tested that until now; it was
 * verified by hand in a browser, which is exactly how the other six bugs in
 * this area survived.
 *
 * These are shell-level: they mount `App` with the network stubbed and
 * assert the wiring between the scope bar, the views, and localStorage.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import App, { NAV } from './App.jsx';
import * as api from './api.js';

const SCOPE = {
  clients: [
    { account_id: 1001, name: 'Candle Bottle', billing_state: 'GA', employees: 10236, synthetic: false },
    { account_id: 2001, name: 'Cascade Retail Partners', billing_state: 'GA', employees: 784, synthetic: true },
  ],
  programs: [{
    program_code: 'GA_JTC',
    name: 'Georgia Jobs Tax Credit',
    citation: 'OCGA § 48-7-40',
    jurisdiction: { level: 'state', code: 'GA', name: 'Georgia' },
    authored_years: [2023, 2024, 2025],
    year_scoped: true,
    calculable: true,
    not_calculable_reason: '',
  }],
  years: { authored: [2023, 2024, 2025], latest: 2025, window_years: 6, default_window: [2023, 2024, 2025] },
  data_source: 'lakehouse',
};

const CLIENT_SCOPE = {
  1001: {
    account_id: 1001, states: ['GA'], payroll_years: [2023, 2024],
    calculable_years: [2023, 2024], payroll_without_statute: [], rows: 384433,
  },
  2001: {
    account_id: 2001, states: ['GA', 'NC'], payroll_years: [2023, 2024, 2025],
    calculable_years: [2023, 2024, 2025], payroll_without_statute: [], rows: 76086,
  },
};

const WORKSPACE = {
  run: {
    step1_calculation_id: 'sha256:abc', onezero_calculation_id: 'sha256:def',
    source_manifest_sha256: 'sha256:ghi', step1_assumption_set_id: 'GDS-STEP1-2026-08-25-v8',
    onezero_assumption_set_id: 'GDS-ONEZERO-2026-08-24-v7', code_commit: 'abc1234',
    created_at: '2026-08-26T12:00:00Z',
  },
  eligibility: {
    employees_with_totals: 10236,
    min_max: { employees_evaluated: 10236, eligible_employees: 539 },
    pay_period: { employees_evaluated: 10236, eligible_employees: 656 },
    reconciliation: { eligible_both: 500, min_max_only: 39, pay_period_only: 156 },
    thresholds: { source_tax_year: 2023 },
    // EligibilityView renders these; the navigation test mounts it for real
    // rather than stubbing the view, so the fixture has to be the real shape.
    denominator_invariant: {
      invariant_holds: true,
      pay_period_gt_min_max: 0,
      pay_period_gt_min_max_over_review_tolerance: 0,
      pay_period_over_52_weeks: 0,
      maximum_weeks_without_review: 53,
    },
    pay_period_controls: {
      source_period_keys: 384418,
      employee_pps_ppe_periods: 382180,
      same_pps_ppe_records_collapsed: 2238,
      conflicting_frequency_periods: 0,
    },
  },
  onezero: { min_max: { overlap_flags: 30 }, pay_period: {} },
  // B5 moved the boundary control into Eligibility, so the fixture has to carry
  // it. The navigation test caught this the moment the panel moved, which is
  // the point of mounting the real view rather than a stub.
  boundary: {
    boundary_complete: true,
    status: 'complete',
    prior_ppe_paid_in_fy_rows: 0,
    crossing_start_rows: 0,
    current_ppe_paid_after_fy_rows: 0,
    earliest_valid_pay_period_start: '2023-07-28',
  },
  comparison: { status: 'awaiting_outputs', first_divergent_stage: null },
  stages: [],
};

const coverageFor = (clientId) => ({
  client_id: clientId,
  cells: [],
  engagements: [],
  totals: {
    identified_usd: '0', claimed_usd: '0', opportunity_usd: '0', exposure_usd: '0',
    cells: 0, exposure_cells: 0, unverified_cells: 0,
  },
});

beforeEach(() => {
  window.localStorage.clear();
  vi.spyOn(api, 'fetchScope').mockResolvedValue(SCOPE);
  vi.spyOn(api, 'fetchClientScope').mockImplementation(
    (id) => Promise.resolve(CLIENT_SCOPE[id] || CLIENT_SCOPE[1001]),
  );
  vi.spyOn(api, 'fetchWorkspace').mockResolvedValue(WORKSPACE);
  vi.spyOn(api, 'refreshWorkspace').mockResolvedValue(WORKSPACE);
  vi.spyOn(api, 'fetchPortfolioCoverage').mockResolvedValue({ clients: [], totals: coverageFor(0).totals });
  // The book is the landing grid now, so the shell cannot mount without it.
  // The old page swallowed a failed read and fell back to the matrix; there is
  // no matrix to fall back to any more, which is why this needs stubbing.
  vi.spyOn(api, 'fetchPortfolioV2').mockResolvedValue({
    total_clients: 2,
    assessed_clients: 1,
    unassessed_clients: 0,
    items: [{
      client_id: 2001,
      client_name: 'Cascade Retail Partners',
      program_code: 'GA_JTC',
      tax_year: 2023,
      priority_band: 'on_the_line',
      priority_rank: 1,
      jobs_margin: -0.4,
      gap_jobs: 0.4,
      identified_usd: '0',
      claimed_usd: '0',
      opportunity_usd: '0',
      is_exposure: false,
    }],
  });
  vi.spyOn(api, 'fetchClientCoverage').mockImplementation((id) => Promise.resolve(coverageFor(id)));
  vi.spyOn(api, 'assessClient').mockResolvedValue({ assessed: [], declined: [] });
});

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

const mount = () => render(<MemoryRouter><App /></MemoryRouter>);

/**
 * The client axis moved OUT of the scope bar and into the URL, so the URL is
 * what these assert against. Rendered inside the router beside `App`, it reads
 * the same location the shell does.
 */
function Where() {
  const location = useLocation();
  return <span data-testid="where">{location.pathname + location.search}</span>;
}

const at = (...entries) => render(
  <MemoryRouter initialEntries={entries}><App /><Where /></MemoryRouter>,
);

const where = () => screen.getByTestId('where').textContent;

/**
 * The nav is a persistent left rail again: a drill ladder showing where you
 * are, and a flat "prove the work" list. Both are always on screen at desktop
 * width, so there is no menu to open first.
 */
const goToView = async (name) => {
  await userEvent.click(screen.getByRole('button', { name }));
};

/** The scope the shell RESOLVED and persisted — client and year, as values. */
const storedScope = () => JSON.parse(window.localStorage.getItem('tcc.scope.v1') || 'null');

/**
 * `/` is the portfolio page: the whole book, assessed or not. "Position by
 * location" is a CLIENT page and lives at /c/:clientId — at portfolio scope it
 * only ever rendered a client picker, because a base year is a fact about one
 * client's payroll and there is deliberately no portfolio view of the grid.
 */
const landed = () => screen.findByRole('heading', { name: 'Targeting' });
/** The client page. Its landmark is still `Position`: `trend` has no nav item. */
const onClientPage = () => screen.findByRole('heading', { name: 'Position by location' });

// ------------------------------------------------------------- it mounts


describe('the navigation is a decided set, not an accumulation', () => {
  // The backend pins its 57 routes in route_inventory.json because a router
  // split once dropped nine endpoints in silence. The sidebar has the same
  // failure mode from the other direction: an entry is cheap to add, nothing
  // forces anyone to justify it, and fifteen of them is a learning curve.
  //
  // Changing this list is allowed. Changing it by accident is not.
  it('offers exactly the entries that answer a question no other entry answers', () => {
    // Twelve became eight. `trend`, `position`, `progress` and `plan` were not
    // deleted — they became the client and portfolio pages, which is why the
    // sections that held them are gone rather than emptied.
    expect(NAV.map((group) => [group.section, group.items.map((item) => item.id)]))
      .toEqual([
        ['What is it worth', ['eligibility', 'onezero']],
        ['What needs a decision', ['ingestion', 'agents']],
        ['Prove it', ['evidence', 'compare', 'rules', 'assumptions']],
      ]);
  });

  it('gives every entry a label and a distinct id', () => {
    const items = NAV.flatMap((group) => group.items);
    const ids = items.map((item) => item.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const item of items) {
      expect(item.label?.length, `missing label on ${item.id}`).toBeGreaterThan(0);
    }
  });
});

describe('the shell opens on the portfolio', () => {
  it('lands on the whole book, because no client is selected yet', async () => {
    mount();
    expect(await landed()).toBeInTheDocument();
    expect(screen.queryByText('Reference Dataset Client', { selector: 'h1' })).not.toBeInTheDocument();
  });

  it('offers no scope bar, because the book has no axis to choose', async () => {
    // A year here was a statement about STATUTE, not about any client:
    // `calculableYears` has no payroll to narrow by at portfolio scope, so it
    // offered every authored GA year and opened on the newest — pinning a
    // client that holds one year of payroll to a year it has none of. The book
    // ranks across every year; the year is chosen after a client is.
    mount();
    await landed();
    expect(screen.queryByRole('region', { name: 'Scope' })).not.toBeInTheDocument();
  });

  it('shows the book at / even when a client was stored last time', async () => {
    // `/` is not "the URL omits the client" — it POSITIVELY means the book.
    // Restoring the stored client there rendered Cascade under the portfolio's
    // own URL, which is the one thing the routing rule forbids.
    window.localStorage.setItem('tcc.scope.v1', JSON.stringify({
      clientId: 2001, programCode: 'all', year: 2023, windowMode: false,
    }));

    render(<MemoryRouter initialEntries={['/']}><App /></MemoryRouter>);

    expect(await landed()).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Position by location' })).not.toBeInTheDocument();
  });
});

// --------------------------------------------------- scope is a dimension


describe('scope survives navigation', () => {
  it('keeps the selected client when moving between views', async () => {
    // B3's entire claim. If this fails, scope is a filter on one page rather
    // than a property of the session. The client now travels in the URL, so
    // that is what must still say 2001 after two view changes.
    at('/c/2001');
    await onClientPage();

    await goToView(/Eligibility/);
    await waitFor(() => expect(screen.getByRole('main')).toHaveAttribute('aria-label', 'Eligibility'));

    // Still Cascade.
    expect(where()).toMatch(/^\/c\/2001\//);
    expect(storedScope().clientId).toBe(2001);

    await goToView(/Monthly employment/);
    await waitFor(() => expect(screen.getByRole('main')).toHaveAttribute('aria-label', 'Monthly employment'));
    expect(where()).toMatch(/^\/c\/2001\//);
    expect(storedScope().clientId).toBe(2001);
  });

  it('restores the scope on reload', async () => {
    const first = at('/c/2001');
    await onClientPage();
    await waitFor(() => expect(storedScope().clientId).toBe(2001));
    first.unmount();

    // The URL omits the client, so the restore has to come from storage rather
    // than from another read.
    api.fetchClientScope.mockClear();
    at('/position');

    await waitFor(() => expect(api.fetchClientScope).toHaveBeenCalledWith(2001));
    expect(storedScope().clientId).toBe(2001);
  });

  it('persists the RESOLVED scope, not the requested one', async () => {
    // Storing an unhonourable selection would reproduce the same notice on
    // every reload, forever.
    window.localStorage.setItem('tcc.scope.v1', JSON.stringify({
      clientId: 1001, programCode: 'all', year: 2019, windowMode: false,
    }));

    // Mounted at the CLIENT url, not `/`. A stored client no longer overrides
    // the root path — see 'shows the book at /'. The year assertion below is
    // this test's actual subject and is unchanged.
    render(<MemoryRouter initialEntries={['/c/1001']}><App /></MemoryRouter>);

    await screen.findByRole('heading', { name: 'Position by location' });
    await waitFor(() => {
      const stored = JSON.parse(window.localStorage.getItem('tcc.scope.v1'));
      expect(stored.year).not.toBe(2019);
      expect(SCOPE.years.authored).toContain(stored.year);
    });
  });

  it('survives a corrupt stored scope rather than failing to boot', async () => {
    window.localStorage.setItem('tcc.scope.v1', 'not json{');
    mount();
    expect(await landed()).toBeInTheDocument();
  });
});

// ------------------------------------------------ the view follows scope


describe('the view re-reads when scope changes', () => {
  const withCascadeInTheMatrix = () => {
    api.fetchPortfolioCoverage.mockResolvedValue({
      clients: [{
        client_id: 2001,
        cells: [{
          client_id: 2001, program_code: 'GA_JTC', tax_year: 2024,
          status: 'assessed', provenance: 'computed', provenance_verified: true,
          identified_usd: '140000', claimed_usd: '0', certified_usd: '0',
          variance_usd: '140000', opportunity_usd: '140000',
          outcome: 'unclaimed', is_exposure: false,
        }],
        totals: {
          identified_usd: '140000', claimed_usd: '0', opportunity_usd: '140000',
          exposure_usd: '0', cells: 1, exposure_cells: 0, unverified_cells: 0,
        },
      }],
      totals: {
        identified_usd: '140000', claimed_usd: '0', opportunity_usd: '140000',
        exposure_usd: '0', cells: 1, exposure_cells: 0, unverified_cells: 0,
      },
    });
  };

  it('asks for the newly selected client', async () => {
    withCascadeInTheMatrix();
    const units = vi.spyOn(api, 'fetchClientUnits')
      .mockResolvedValue({ calculation_state: 'not_calculated', message: 'x', items: [] });
    at('/');
    await landed();

    // Portfolio scope describes no single client, so nothing has been asked
    // for 2001 yet. Picking it is what must issue the reads.
    expect(api.fetchClientScope).not.toHaveBeenCalledWith(2001);

    await userEvent.click(await screen.findByRole('button', { name: 'Open Cascade Retail Partners' }));

    await waitFor(() => expect(api.fetchClientScope).toHaveBeenCalledWith(2001));
    // The client page is tabbed, and only the open section reads. The location
    // grid opens first; "What was claimed" reads when somebody opens it —
    // and then for THIS client.
    await waitFor(() => expect(units).toHaveBeenCalledWith(2001, expect.anything()));
    expect(api.fetchClientCoverage).not.toHaveBeenCalledWith(2001, expect.anything());
    await userEvent.click(await screen.findByRole('tab', { name: 'What was claimed' }));
    await waitFor(() => expect(api.fetchClientCoverage).toHaveBeenCalledWith(2001, expect.anything()));
  });

  it('drilling from the portfolio matrix sets scope, not just the view', async () => {
    withCascadeInTheMatrix();

    at('/');
    await landed();

    // The matrix IS the landing page now, so there is nothing to open first.
    await userEvent.click(await screen.findByRole('button', { name: 'Open Cascade Retail Partners' }));

    // Scope must follow, or the shell and the view disagree about who is being
    // looked at. The client axis lives in the URL and in the persisted scope.
    await waitFor(() => expect(where()).toMatch(/^\/c\/2001(\?|$|\/)/));
    await waitFor(() => expect(storedScope().clientId).toBe(2001));
  });
});

// -------------------------------------------------------------- failure


describe('URL drives the active scope and page', () => {
  it('uses the route and query string as the source of truth for client and year', async () => {
    at('/c/2001/position?year=2025');

    // `position` is not a nav id, so the route resolves to the client page and
    // the landmark keeps its default name.
    await waitFor(() => expect(screen.getByRole('main')).toHaveAttribute('aria-label', 'Position'));
    await waitFor(() => expect(api.fetchClientScope).toHaveBeenCalledWith(2001));

    // The year axis left the client page on purpose — the grid IS the year
    // dimension there — so the resolved scope is what carries it now.
    await waitFor(() => {
      expect(storedScope().clientId).toBe(2001);
      expect(storedScope().year).toBe(2025);
    });
  });

  it('falls back to the stored scope only when the URL omits the client and year', async () => {
    window.localStorage.setItem('tcc.scope.v1', JSON.stringify({
      clientId: 1001, programCode: 'all', year: 2024, windowMode: false,
    }));

    const first = at('/position');

    await waitFor(() => expect(screen.getByRole('main')).toHaveAttribute('aria-label', 'Position'));
    await waitFor(() => expect(api.fetchClientScope).toHaveBeenCalledWith(1001));
    await waitFor(() => {
      expect(storedScope().clientId).toBe(1001);
      expect(storedScope().year).toBe(2024);
    });

    // ONLY when it omits them. The same stored scope must lose to a URL that
    // names both, or storage stops being a fallback and becomes an override.
    first.unmount();
    window.localStorage.setItem('tcc.scope.v1', JSON.stringify({
      clientId: 1001, programCode: 'all', year: 2024, windowMode: false,
    }));
    api.fetchClientScope.mockClear();

    at('/c/2001/position?year=2025');

    await waitFor(() => expect(api.fetchClientScope).toHaveBeenCalledWith(2001));
    expect(api.fetchClientScope).not.toHaveBeenCalledWith(1001);
    await waitFor(() => {
      expect(storedScope().clientId).toBe(2001);
      expect(storedScope().year).toBe(2025);
    });
  });
});

describe('a broken scope endpoint degrades honestly', () => {
  it('still mounts and says what went wrong', async () => {
    api.fetchScope.mockRejectedValue(new Error('scope 503'));
    mount();

    expect(await landed()).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Scope' })).toHaveTextContent('scope 503');
  });
});
