import { render as rawRender, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// The grid keeps its sort and filter in the query string, so it needs a router.
// Harness only — no assertion changes.
const render = (ui) => rawRender(<MemoryRouter>{ui}</MemoryRouter>);
import { afterEach, describe, expect, it, vi } from 'vitest';
import ClientPage from './ClientPage.jsx';
import PortfolioPage from './PortfolioPage.jsx';

vi.mock('../api.js', async () => {
  const actual = await vi.importActual('../api.js');
  return {
    ...actual,
    fetchClientUnits: vi.fn().mockResolvedValue({ calculation_state: 'not_calculated', message: 'x', items: [] }),
    fetchInYearProgress: vi.fn(),
    fetchProximity: vi.fn(),
    fetchPortfolioV2: vi.fn(),
    fetchPortfolioCoverage: vi.fn().mockResolvedValue({ clients: [], totals: {} }),
    fetchClientCoverage: vi.fn().mockResolvedValue({ cells: [], totals: {} }),
    simulateOneZero: vi.fn(),
    simulateUnit: vi.fn(),
  };
});

const api = await import('../api.js');

/** GA-016 as Gold holds it after WI-11: a TY2020 base, and TY2025 below minimum. */
const GRID = {
  calculation_state: 'calculated',
  run: { run_id: 'r1', produced_at: '2026-09-24T04:45:14Z' },
  items: [
    { worksite_id: 'GA_GA-016', tax_year: 2020, method: 'min_max', average_headcount: 7.33, base_average_headcount: 7.33,
      net_new_vs_base: 0, threshold: null, is_base_year: true, status: 'base', qualified: false, annual_credit_usd: '0', tier_source: 'unassigned' },
    { worksite_id: 'GA_GA-016', tax_year: 2025, method: 'min_max', average_headcount: 7.67, base_average_headcount: 7.33,
      net_new_vs_base: 0.34, threshold: 2, is_base_year: false, status: 'below_minimum', qualified: false, annual_credit_usd: '0', tier_source: 'unassigned' },
  ],
  total: 2,
  months: [],
  installments: [],
  unit_totals: [{ worksite_id: 'GA_GA-016', total_annual_credit_usd: '0', final_high_water_mark: 14, total_tranche_lifetime_usd: '0' }],
  units: [{ worksite_id: 'GA_GA-016', name: 'Valdosta Site 16' }],
  years: [2020, 2025],
};

const UNIT_PROJECTION = {
  scope: { client_id: 2001, worksite_id: 'GA_GA-016', state: 'GA', tax_year: 2025, method: 'min_max' },
  detail: 'Added 2 full-time heads at GA_GA-016',
  base_year: 2020,
  series_years: [2020, 2025],
  eligibility_floors: { min_weekly_hours: 35, min_weekly_wages: 680 },
  method_note: 'Priced as the location grid prices it.',
  baseline: { average_headcount: 7.67, net_new_vs_base: 0.34, threshold: 2, jobs_margin: -1.66, status: 'below_minimum', annual_credit_usd: 0, series_credit_usd: 0 },
  projected: { average_headcount: 9.67, net_new_vs_base: 2.34, threshold: 2, jobs_margin: 0.34, status: 'above_minimum', annual_credit_usd: 8190, series_credit_usd: 8190 },
  delta: { average_headcount: 2, net_new_vs_base: 2, annual_credit_usd: 8190, series_credit_usd: 8190 },
};

const SCOPE_OPTIONS = {
  clients: [
    { account_id: 2001, name: 'Cascade', industry: 'Retail' },
    { account_id: 2002, name: 'Northwind' },
  ],
  programs: [{ program_code: 'GA_JTC', calculable: true, jurisdiction: { code: 'GA', level: 'state' } }],
};

afterEach(() => vi.clearAllMocks());

describe('a client page carries the questions that need a single client', () => {
  // Both refused portfolio scope, which is why neither was ever really a
  // destination of its own. They are tabs now: stacked, What-if sat four and
  // a half screens below the grid it answers questions about.
  it('says the client’s industry beside its name (WI-20)', () => {
    render(
      <ClientPage
        clientName="Cascade"
        scope={{ clientId: 2001, programCode: 'GA_JTC', year: 2023 }}
        scopeOptions={SCOPE_OPTIONS}
      />,
    );
    const crumbs = screen.getByRole('navigation', { name: 'Breadcrumb' });
    expect(crumbs).toHaveTextContent('Cascade');
    expect(crumbs).toHaveTextContent('Retail');
  });

  it('opens on the location grid, with the other sections one click away', async () => {
    render(
      <ClientPage
        clientName="Cascade"
        scope={{ clientId: 2001, programCode: 'GA_JTC', year: 2023 }}
        scopeOptions={SCOPE_OPTIONS}
      />,
    );

    const tabs = screen.getAllByRole('tab').map((t) => t.textContent);
    expect(tabs).toEqual(['Position by location', 'What was claimed', 'How am I doing', 'What-if']);
    expect(screen.getByRole('tab', { name: 'Position by location' })).toHaveAttribute('aria-selected', 'true');
    // Only the open section reads.
    await waitFor(() => expect(api.fetchClientUnits).toHaveBeenCalled());
    expect(api.fetchInYearProgress).not.toHaveBeenCalled();
  });

  it('renders progress and the what-if levers on their tabs', async () => {
    api.fetchClientUnits.mockResolvedValue({ calculation_state: 'not_calculated', message: 'x', items: [] });
    api.fetchInYearProgress.mockResolvedValue({
      on_track: true, closed_months: 6, projection: {}, cohort: null,
    });

    render(
      <ClientPage
        clientName="Cascade"
        scope={{ clientId: 2001, programCode: 'GA_JTC', year: 2023 }}
        scopeOptions={SCOPE_OPTIONS}
      />,
    );

    await userEvent.click(screen.getByRole('tab', { name: 'How am I doing' }));
    await waitFor(() => expect(api.fetchInYearProgress).toHaveBeenCalled());

    await userEvent.click(screen.getByRole('tab', { name: 'What-if' }));
    expect(await screen.findByText(/What would change the answer|lever/i)).toBeInTheDocument();
  });

  it('a Below minimum pill opens What-if on that location, pre-filled and run', async () => {
    api.fetchClientUnits.mockResolvedValue(GRID);
    api.simulateUnit.mockResolvedValue(UNIT_PROJECTION);
    render(
      <ClientPage
        clientName="Cascade"
        scope={{ clientId: 2001, programCode: 'GA_JTC', year: 2025 }}
        scopeOptions={SCOPE_OPTIONS}
      />,
    );

    await userEvent.click(await screen.findByRole('button', { name: /Below minimum: open What-if for GA_GA-016 TY2025/ }));

    expect(screen.getByRole('tab', { name: 'What-if' })).toHaveAttribute('aria-selected', 'true');
    await waitFor(() => expect(api.simulateUnit).toHaveBeenCalledWith(expect.objectContaining({
      clientId: 2001, worksiteId: 'GA_GA-016', taxYear: 2025, method: 'min_max',
      action: 'add_headcount', magnitude: 2,
    })));
    // The filter is stated in the header, and it is the location, not the client.
    expect(screen.getByRole('combobox', { name: /Filter the what-if to one location/ })).toHaveValue('GA_GA-016');
    expect(await screen.findByText('Projection · GA_GA-016')).toBeInTheDocument();
    // The client-wide simulator must not be what answered.
    expect(api.simulateOneZero).not.toHaveBeenCalled();
  });

  it('a base year is a statement, not a way into What-if', async () => {
    api.fetchClientUnits.mockResolvedValue(GRID);
    render(
      <ClientPage
        clientName="Cascade"
        scope={{ clientId: 2001, programCode: 'GA_JTC', year: 2025 }}
        scopeOptions={SCOPE_OPTIONS}
      />,
    );
    await screen.findByRole('button', { name: /Below minimum: open What-if/ });
    expect(screen.queryByRole('button', { name: /Base year: open What-if/ })).not.toBeInTheDocument();
  });

  it('a pasted What-if link renders the same projection cold', async () => {
    api.fetchClientUnits.mockResolvedValue(GRID);
    api.simulateUnit.mockResolvedValue(UNIT_PROJECTION);
    rawRender(
      <MemoryRouter initialEntries={['/c/2001?ctab=whatif&wunit=GA_GA-016&wyear=2025&wmethod=min_max&wlever=add_headcount&wmag=2&wrun=1']}>
        <ClientPage
          clientName="Cascade"
          scope={{ clientId: 2001, programCode: 'GA_JTC', year: 2025 }}
          scopeOptions={SCOPE_OPTIONS}
        />
      </MemoryRouter>,
    );
    await waitFor(() => expect(api.simulateUnit).toHaveBeenCalledTimes(1));
    expect(api.fetchInYearProgress).not.toHaveBeenCalled();
  });
});

describe('a stack built on another page is here when the client page opens (29 Sep)', () => {
  it('takes the saved stack for this client into the URL, and not another client’s', async () => {
    const store = await import('../lib/whatIfStack.js');
    store.writeStack({ clientId: 2001, taxYear: 2026, method: 'min_max' }, [{ token: 'n1', hours: 1.5, raise: 0 }]);
    api.fetchClientUnits.mockResolvedValue({ calculation_state: 'not_calculated', message: 'x', items: [] });

    rawRender(
      <MemoryRouter initialEntries={['/c/2001?ctab=whatif']}>
        <ClientPage clientName="Cascade" scope={{ clientId: 2001, programCode: 'GA_JTC', year: 2025 }} scopeOptions={SCOPE_OPTIONS} />
      </MemoryRouter>,
    );
    expect(await screen.findByText(/this employee works differently/)).toBeInTheDocument();
    expect(screen.getByRole('spinbutton', { name: /More hours a week for/ })).toHaveValue(1.5);

    rawRender(
      <MemoryRouter initialEntries={['/c/2002?ctab=whatif']}>
        <ClientPage clientName="Northwind" scope={{ clientId: 2002, programCode: 'GA_JTC', year: 2025 }} scopeOptions={SCOPE_OPTIONS} />
      </MemoryRouter>,
    );
    expect(screen.getAllByText(/this employee works differently/)).toHaveLength(1);
    store.writeStack({ clientId: 2001, taxYear: 2026, method: 'min_max' }, []);
  });
});
describe('the book is one ranked grid, not two tabs', () => {
  // "Who to call" read the same claims as the matrix and kept only cells within
  // one job of a threshold. Splitting them meant a reader had to know which tab
  // held the answer before they knew what the answer was.
  const ROWS = [
    {
      client_id: 2001, client_name: 'Cascade', program_code: 'GA_JTC', tax_year: 2023,
      priority_band: 'on_the_line', priority_rank: 1, jobs_margin: -0.4, gap_jobs: 0.4,
      identified_usd: '0', claimed_usd: '0', opportunity_usd: '0', is_exposure: false,
    },
    {
      client_id: 2002, client_name: 'Northwind', program_code: 'GA_JTC', tax_year: 2023,
      priority_band: 'unclaimed_at_scale', priority_rank: 2, jobs_margin: 48.0, gap_jobs: 0,
      identified_usd: '607110', claimed_usd: '0', opportunity_usd: '607110', is_exposure: false,
    },
  ];

  const draw = (items = ROWS) => {
    api.fetchPortfolioV2.mockResolvedValue({
      total_clients: 5, assessed_clients: 4, unassessed_clients: 1, items,
    });
    return render(
      <PortfolioPage scopeOptions={SCOPE_OPTIONS} scope={{ clientId: 'portfolio', year: 2023 }} />,
    );
  };

  it('asks for priority order, not a dollar sort', async () => {
    draw();
    await waitFor(() => expect(api.fetchPortfolioV2).toHaveBeenCalled());
    expect(api.fetchPortfolioV2).toHaveBeenCalledWith(
      expect.objectContaining({ sort: 'priority', order: 'asc' }),
    );
  });

  it('asks for NO tax year', async () => {
    // The book ranks across every year a client holds. A year filter buries an
    // unclaimed year that is still recoverable retroactively — and the year on
    // offer was a STATUTE year, so a client holding one year of payroll was
    // pinned to a year it has none of and shown a figure for it.
    draw();
    await waitFor(() => expect(api.fetchPortfolioV2).toHaveBeenCalled());
    expect(api.fetchPortfolioV2.mock.calls[0][0]).not.toHaveProperty('year');
  });

  it('reads the book once', async () => {
    // Two reads of one ranking is how somebody ends up comparing two orderings
    // of the same data and concluding there are two answers.
    draw();
    await screen.findByRole('button', { name: 'Open Cascade' });
    expect(api.fetchPortfolioV2).toHaveBeenCalledTimes(1);
  });

  it('shows every client in one grid, whatever their band', async () => {
    draw();
    expect(await screen.findByRole('button', { name: 'Open Cascade' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open Northwind' })).toBeInTheDocument();
    expect(screen.getByText('On the line')).toBeInTheDocument();
    // "Identified", not "Unclaimed": whether they already claimed it is a fact
    // about a filing we do not hold.
    expect(screen.getByText('Identified', { selector: '.tcc-band' })).toBeInTheDocument();
  });

  it('headlines a client on the line in JOBS, never in dollars', async () => {
    // They earn $0 today. A dollar value here is exactly what buries them.
    draw();
    expect(await screen.findByText('0.4 to qualify')).toBeInTheDocument();
  });

  it('says the counts come from the API, not from the rows on screen', async () => {
    draw();
    expect(await screen.findByText(/5 clients · 4 assessed/)).toBeInTheDocument();
  });

  it('expands a client to EVERY programme-year, not the selected one', async () => {
    // "Which programmes, which years" is one click, not a second screen — and
    // the book is not year-scoped, so narrowing this to one year would hide
    // the retroactive years that are the reason to call.
    // The resolved value is set HERE rather than relied on from the module
    // factory: `clearAllMocks` between tests takes the implementation with it.
    api.fetchClientCoverage.mockResolvedValue({ cells: [], totals: {} });
    draw();
    await userEvent.click(await screen.findByRole('button', { name: /Expand Cascade/ }));
    await waitFor(() => expect(api.fetchClientCoverage).toHaveBeenCalledWith(2001, {}));
  });

  it('asks Copilot about the row, not about the selected scope', async () => {
    // The shell is on portfolio scope. An ask that inherited it would answer
    // about nobody, or about whichever client happened to be selected.
    const onAskCopilot = vi.fn();
    api.fetchPortfolioV2.mockResolvedValue({
      total_clients: 5, assessed_clients: 4, unassessed_clients: 1, items: ROWS,
    });
    render(
      <PortfolioPage
        scopeOptions={SCOPE_OPTIONS}
        scope={{ clientId: 'portfolio', year: 2023 }}
        onAskCopilot={onAskCopilot}
      />,
    );

    const ask = await screen.findByRole('button', { name: 'Ask Copilot about Cascade' });
    await userEvent.click(ask);

    expect(onAskCopilot).toHaveBeenCalledWith(
      expect.stringContaining('Cascade'),
      { clientId: 2001, taxYear: 2023 },
    );
  });

  it('states why the order is not a dollar value', async () => {
    draw();
    expect(await screen.findByText(/ranking by value buries the\s+customer most worth a call/))
      .toBeInTheDocument();
  });
});

