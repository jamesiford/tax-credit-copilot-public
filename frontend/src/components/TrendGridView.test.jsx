import { render as rawRender, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// The grid keeps its sort and filter in the query string, so it needs a router.
// Harness only — no assertion changes.
const render = (ui) => rawRender(<MemoryRouter>{ui}</MemoryRouter>);
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import TrendGridView from './TrendGridView.jsx';

vi.mock('../api.js', async () => {
  const actual = await vi.importActual('../api.js');
  return {
    ...actual,
    fetchClientUnits: vi.fn(),
    fetchClientUnit: vi.fn(),
    fetchUnitRebase: vi.fn(),
    saveBaseYear: vi.fn(),
    runClientCalculation: vi.fn(),
  };
});

const api = await import('../api.js');

const scope = { clientId: 2001, programCode: 'GA_JTC', year: 2023 };

// `trendState` resolves the jurisdiction from the PROGRAMME, not the client, so
// the programme list is the part of scopeOptions that matters here.
const scopeOptions = {
  programs: [{ program_code: 'GA_JTC', calculable: true, jurisdiction: { code: 'GA', level: 'state' } }],
  clients: [{ id: 2001, name: 'Cascade' }],
};

/** One warehouse row, in the Gold vocabulary the reader publishes. */
function goldRow(over = {}) {
  return {
    worksite_id: 'GA_GA-001',
    tax_year: 2023,
    method: 'min_max',
    program_code: 'GA_JTC',
    average_headcount: 25.92,
    base_average_headcount: 21.5,
    net_new_vs_base: 4.42,
    threshold: 2,
    tier: 1,
    designation: 'Tier 1',
    tier_source: 'designation',
    per_job_usd: '4000.0000',
    annual_credit_usd: '17680.0000',
    qualified: true,
    is_base_year: false,
    status: 'qualified',
    high_water_mark: 26.17,
    months_with_headcount: 12,
    unreachable_months: '',
    ...over,
  };
}

function calculatedPayload(over = {}) {
  return {
    calculation_state: 'calculated',
    run: { run_id: '1ef66984739b4e22986ec57603fe8a7c', produced_at: '2026-09-01T10:00:00Z' },
    newer_run_in_flight: false,
    items: [goldRow()],
    total: 1,
    months: [{
      worksite_id: 'GA_GA-001',
      tax_year: 2023,
      method: 'min_max',
      total: 311.0,
      average_headcount: 25.92,
      unreachable_months: '',
      ...Object.fromEntries(Array.from({ length: 12 }, (_, i) => [`month_${String(i + 1).padStart(2, '0')}`, 26])),
    }],
    installments: [
      { worksite_id: 'GA_GA-001', tax_year: 2023, claimable_usd: '25095.0000', projected: false, creation_year: 2021 },
    ],
    unit_totals: [{
      worksite_id: 'GA_GA-001',
      total_annual_credit_usd: '120820.0000',
      final_high_water_mark: 26.17,
      total_tranche_lifetime_usd: '128730.0000',
    }],
    units: [{ worksite_id: 'GA_GA-001', name: 'Peachtree', county: 'Fulton', city: 'Atlanta' }],
    years: [2023],
    ...over,
  };
}

afterEach(() => { vi.clearAllMocks(); });

describe('the calculation state is a statement, not an empty grid', () => {
  it('offers a run rather than reporting nothing when no run exists', async () => {
    // "The pipeline has not reached this yet" and "we looked and found nothing"
    // are different claims about a client's payroll. Only the second is a
    // finding, and a grid of zeroes asserts the second while meaning the first.
    api.fetchClientUnits.mockResolvedValue({
      calculation_state: 'not_calculated',
      message: 'Not assessed yet. It carries no figure — not a zero.',
      run: null,
      items: [],
      months: [],
      installments: [],
      unit_totals: [],
      units: [],
      years: [],
    });

    render(<TrendGridView scope={scope} scopeOptions={scopeOptions} />);

    expect(await screen.findByRole('heading', { name: /Awaiting the next run/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Run TY2023 now/i })).toBeInTheDocument();
    // Nothing that looks like a priced answer.
    expect(screen.queryByText('$0')).not.toBeInTheDocument();
    expect(screen.queryByText(/Claimable, stair-step/i)).not.toBeInTheDocument();
  });

  it('runs the calculation and re-reads the warehouse', async () => {
    api.fetchClientUnits
      .mockResolvedValueOnce({ calculation_state: 'not_calculated', message: 'Not assessed yet.', items: [] })
      .mockResolvedValue(calculatedPayload());
    api.runClientCalculation.mockResolvedValue({ run_id: 'abc' });

    render(<TrendGridView scope={scope} scopeOptions={scopeOptions} />);
    await userEvent.click(await screen.findByRole('button', { name: /Run TY2023 now/i }));

    await waitFor(() => expect(api.runClientCalculation).toHaveBeenCalledWith(2001, { year: 2023, state: 'GA' }));
    // The run does not paint its own result: the grid re-reads Gold.
    await waitFor(() => expect(api.fetchClientUnits).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('Peachtree')).toBeInTheDocument();
  });
});

describe('the grid renders what the warehouse published', () => {
  it('names the run that produced the figures', async () => {
    api.fetchClientUnits.mockResolvedValue(calculatedPayload());
    render(<TrendGridView scope={scope} scopeOptions={scopeOptions} />);
    expect(await screen.findByText(/1ef66984739b/)).toBeInTheDocument();
  });

  it('says so when a newer run is in flight', async () => {
    api.fetchClientUnits.mockResolvedValue(calculatedPayload({ newer_run_in_flight: true }));
    render(<TrendGridView scope={scope} scopeOptions={scopeOptions} />);
    expect(await screen.findByText(/newer run is in flight/i)).toBeInTheDocument();
  });

  it('sums no money of its own — the totals arrive from SQL', async () => {
    api.fetchClientUnits.mockResolvedValue(calculatedPayload());
    render(<TrendGridView scope={scope} scopeOptions={scopeOptions} />);
    // $120,820 is SUM(annual_credit_usd) as the reader computed it. If the
    // component re-derived it from the single visible row it would show
    // $17,680 instead.
    expect(await screen.findByText('$120,820')).toBeInTheDocument();
  });
});

describe('the unit header is a row, and nothing real was lost in the collapse', () => {
  // The card cost ~400px before the first data row, per unit. Two things inside
  // it were load-bearing and are the reason this is tested rather than eyeballed.
  const mountGrid = async () => {
    api.fetchClientUnits.mockResolvedValue(calculatedPayload());
    render(<TrendGridView scope={scope} scopeOptions={scopeOptions} />);
    return screen.findByRole('button', { name: /^Detail$/ });
  };

  it('shows the unit as a row with its id and the figures that decide something', async () => {
    await mountGrid();

    expect(screen.getByText('GA_GA-001')).toBeInTheDocument();
    expect(screen.getByText('Peachtree')).toBeInTheDocument();
    // Also a column header on the years table, hence getAllByText.
    expect(screen.getAllByText('Net new').length).toBeGreaterThan(0);
    expect(screen.getByText('Credit')).toBeInTheDocument();
  });

  it('keeps the plain-English reading reachable for the unit', async () => {
    // The best summary on the page. Behind the expand, never deleted.
    const more = await mountGrid();
    await userEvent.click(more);

    expect(await screen.findByText(/net-new/i)).toBeInTheDocument();
  });

  it('keeps the tranche chips, which are a different grain from the year rows', async () => {
    const more = await mountGrid();
    await userEvent.click(more);

    expect(await screen.findByText('YR1')).toBeInTheDocument();
    // Compact in a chip; `money` abbreviates above a thousand.
    expect(screen.getByText('$25k')).toBeInTheDocument();
  });

  it('does not make the years table cost the tranche detail', async () => {
    // Expanding every unit's detail by default is what pushed the first data
    // row DOWN the page; the years table must not drag it along.
    await mountGrid();

    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.queryByText('YR1')).not.toBeInTheDocument();
  });

  it('marks a projected installment as projected', async () => {
    // A forecast and a measured installment must not render alike.
    api.fetchClientUnits.mockResolvedValue(calculatedPayload({
      installments: [
        { worksite_id: 'GA_GA-001', tax_year: 2023, claimable_usd: '25095.0000', projected: false, creation_year: 2021 },
        { worksite_id: 'GA_GA-001', tax_year: 2024, claimable_usd: '25095.0000', projected: true, creation_year: 2021 },
      ],
    }));
    render(<TrendGridView scope={scope} scopeOptions={scopeOptions} />);
    await userEvent.click(await screen.findByRole('button', { name: /^Detail$/ }));

    const projected = await screen.findByTitle(/projected, not a measured installment/i);
    expect(projected).toHaveClass('projected');
    expect(screen.getByTitle(/· measured installment/i)).not.toHaveClass('projected');
  });
});

describe('every location-year carries its own designation', () => {
  it('shows it right of the tax year on every row, as the partner reads it down the column', async () => {
    api.fetchClientUnits.mockResolvedValue(calculatedPayload({
      items: [
        goldRow({ tax_year: 2020, is_base_year: true, status: 'base', tier: 1, designation: 'T1', tier_source: 'prototype' }),
        goldRow({ tax_year: 2021, status: 'above_minimum', tier: 1, designation: 'T1 B40', tier_source: 'prototype' }),
        goldRow({ tax_year: 2022, status: 'above_minimum', tier: 1, designation: 'T1', tier_source: 'prototype' }),
      ],
    }));
    render(<TrendGridView scope={scope} scopeOptions={scopeOptions} />);

    const header = await screen.findByRole('columnheader', { name: /Designation/ });
    const cells = [...header.closest('tr').children].map((th) => th.textContent);
    expect(cells.findIndex((t) => /Designation/.test(t))).toBe(cells.findIndex((t) => /Tax year/.test(t)) + 1);

    const rows = screen.getAllByRole('row').filter((r) => /TY20(20|21|22)/.test(r.textContent));
    expect(rows.map((r) => r.querySelector('.trend-tier')?.textContent)).toEqual(['T1', 'T1 B40', 'T1']);
    // The header summarises; the column says which year.
    expect(screen.getByText('Designation varies')).toBeInTheDocument();
    expect(screen.getByTitle(/40 least developed counties · TY2021/)).toBeInTheDocument();
  });

  it('says Unassigned where no designation is on record', async () => {
    api.fetchClientUnits.mockResolvedValue(calculatedPayload({
      items: [goldRow({ tier: null, designation: null, tier_source: 'unassigned' })],
    }));
    render(<TrendGridView scope={scope} scopeOptions={scopeOptions} />);
    const rows = await screen.findAllByRole('row');
    const cell = rows.map((r) => r.querySelector('td.trend-tier')).find(Boolean);
    expect(cell).toHaveTextContent('Unassigned');
  });
});

describe('the Reading pill is the way into What-if', () => {
  const payload = () => calculatedPayload({
    items: [
      goldRow({ tax_year: 2020, is_base_year: true, status: 'base', net_new_vs_base: 0, threshold: null }),
      goldRow({ tax_year: 2023, status: 'below_minimum', qualified: false, net_new_vs_base: 0.34, threshold: 2 }),
      goldRow({ tax_year: 2024, status: 'above_minimum', net_new_vs_base: 6.1 }),
    ],
  });

  it('a Below minimum pill hands over the location, year, method and the hire it would take', async () => {
    api.fetchClientUnits.mockResolvedValue(payload());
    const onWhatIf = vi.fn();
    render(<TrendGridView scope={scope} scopeOptions={scopeOptions} onWhatIf={onWhatIf} />);

    await userEvent.click(await screen.findByRole('button', { name: 'Below minimum: open What-if for GA_GA-001 TY2023' }));
    expect(onWhatIf).toHaveBeenCalledWith({
      ctab: 'whatif', wunit: 'GA_GA-001', wstack: '', wemp: '', wyear: '2023', wmethod: 'min_max',
      wlever: 'add_headcount', wmag: '2', wrun: '1',
    });
  });

  it('an Above minimum pill scopes What-if without pre-filling a lever', async () => {
    api.fetchClientUnits.mockResolvedValue(payload());
    const onWhatIf = vi.fn();
    render(<TrendGridView scope={scope} scopeOptions={scopeOptions} onWhatIf={onWhatIf} />);

    await userEvent.click(await screen.findByRole('button', { name: 'Above minimum: open What-if for GA_GA-001 TY2024' }));
    expect(onWhatIf).toHaveBeenCalledWith(expect.objectContaining({ wunit: 'GA_GA-001', wyear: '2024', wlever: '', wrun: '' }));
  });

  it('a base year stays a statement', async () => {
    api.fetchClientUnits.mockResolvedValue(payload());
    render(<TrendGridView scope={scope} scopeOptions={scopeOptions} onWhatIf={vi.fn()} />);
    await screen.findByRole('button', { name: /Below minimum: open What-if/ });
    expect(screen.queryByRole('button', { name: /Base year/ })).not.toBeInTheDocument();
  });

  it('without a What-if to open, no pill pretends to be a button', async () => {
    api.fetchClientUnits.mockResolvedValue(payload());
    render(<TrendGridView scope={scope} scopeOptions={scopeOptions} />);
    await screen.findAllByText('Below minimum');
    expect(screen.queryByRole('button', { name: /open What-if/ })).not.toBeInTheDocument();
  });
});

describe('a slow fetch for the previous client cannot paint under the new name', () => {
  it('drops rows that belong to a scope the user has left', async () => {
    let releaseFirst;
    api.fetchClientUnits.mockImplementationOnce(
      () => new Promise((resolve) => { releaseFirst = () => resolve(calculatedPayload()); }),
    ).mockResolvedValue({ calculation_state: 'not_calculated', message: 'Not yet calculated.', items: [] });

    const { rerender } = render(<TrendGridView scope={scope} scopeOptions={scopeOptions} />);
    rerender(
      <MemoryRouter>
        <TrendGridView
          scope={{ ...scope, clientId: 2002 }}
          scopeOptions={{ ...scopeOptions, clients: [{ id: 2002, name: 'Northwind' }] }}
        />
      </MemoryRouter>,
    );
    releaseFirst();

    // Cascade's location must never appear while Northwind is selected. Waiting
    // on the refetch rather than on rendered text keeps this honest: the guard
    // holds whatever the second payload turns out to say.
    await waitFor(() => expect(api.fetchClientUnits).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByText('Peachtree')).not.toBeInTheDocument());
  });
});


describe('the base-year picker (WI-21)', () => {
  const monthsFor = (year) => ({
    worksite_id: 'GA_GA-001', tax_year: year, method: 'min_max', total: 312, average_headcount: 26,
    unreachable_months: '', months_with_headcount: 12,
    ...Object.fromEntries(Array.from({ length: 12 }, (_, i) => [`month_${String(i + 1).padStart(2, '0')}`, 26])),
  });
  const grid = () => calculatedPayload({
    items: [
      goldRow({ tax_year: 2020, is_base_year: true, status: 'base', net_new_vs_base: 0, threshold: null, months_reachable: 12 }),
      goldRow({ tax_year: 2021, status: 'above_minimum', net_new_vs_base: 3, months_reachable: 12 }),
      goldRow({ tax_year: 2022, status: 'below_minimum', qualified: false, net_new_vs_base: 1, months_reachable: 12 }),
    ],
    months: [monthsFor(2020), monthsFor(2021), monthsFor(2022)],
  });
  const REBASE = {
    worksite_id: 'GA_GA-001', base_year: 2021, inferred_base_year: 2020,
    total_annual_credit_usd: 0, run_total_annual_credit_usd: 17680, delta_annual_credit_usd: -17680,
    years: [
      { tax_year: 2020, role: 'before_base', status: 'before_base' },
      { tax_year: 2021, role: 'base', status: 'base' },
      { tax_year: 2022, role: 'evaluated', year_number: 1, status: 'below_minimum', qualified: false, net_new_vs_base: 0, annual_credit_usd: 0 },
    ],
  };

  it('offers the complete years, marking the one the run used', async () => {
    api.fetchClientUnits.mockResolvedValue(grid());
    render(<TrendGridView scope={scope} scopeOptions={scopeOptions} onWhatIf={vi.fn()} />);
    const picker = await screen.findByRole('combobox', { name: 'Base year for GA_GA-001' });
    expect(picker).toHaveValue('2020');
    expect([...picker.options].map((o) => o.textContent)).toEqual(['TY2020 (run)', 'TY2021', 'TY2022']);
  });

  it('re-prices the block against the chosen year, greys what came before, and says it is not saved', async () => {
    api.fetchClientUnits.mockResolvedValue(grid());
    api.fetchUnitRebase.mockResolvedValue(REBASE);
    const onWhatIf = vi.fn();
    render(<TrendGridView scope={scope} scopeOptions={scopeOptions} onWhatIf={onWhatIf} />);
    await userEvent.selectOptions(await screen.findByRole('combobox', { name: 'Base year for GA_GA-001' }), '2021');

    await waitFor(() => expect(api.fetchUnitRebase).toHaveBeenCalledWith(2001, 'GA_GA-001', expect.objectContaining({ baseYear: 2021 })));
    const banner = await screen.findByRole('status');
    expect(banner).toHaveTextContent('Base year set to TY2021');
    expect(banner).toHaveTextContent('not saved');
    expect(banner).toHaveTextContent('from TY2020');
    expect(screen.getByText('Before base')).toBeInTheDocument();
    expect(screen.getByText('YR1')).toBeInTheDocument();
    const before = screen.getAllByRole('row').find((r) => /TY2020/.test(r.textContent) && r.classList.contains('trend-year'));
    expect(before).toHaveClass('trend-before-base');
    // What-if prices against the run's base, so it steps aside on a rebased block.
    expect(screen.queryByRole('button', { name: /open What-if/ })).not.toBeInTheDocument();
  });

  it('saving records the choice with its reason and says a recalculation is running', async () => {
    api.fetchClientUnits.mockResolvedValue(grid());
    api.fetchUnitRebase.mockResolvedValue(REBASE);
    api.saveBaseYear.mockResolvedValue({ recorded: true, recalculation: 'started' });
    render(<TrendGridView scope={scope} scopeOptions={scopeOptions} />);
    await userEvent.selectOptions(await screen.findByRole('combobox', { name: 'Base year for GA_GA-001' }), '2021');
    await userEvent.type(await screen.findByRole('textbox', { name: /Reason for saving TY2021/ }), 'the partner\u2019s example');
    await userEvent.click(screen.getByRole('button', { name: 'Save TY2021 as the base year' }));

    await waitFor(() => expect(api.saveBaseYear).toHaveBeenCalledWith(
      2001, 'GA_GA-001', expect.objectContaining({ baseYear: 2021, justification: 'the partner\u2019s example' }),
    ));
    expect(await screen.findByText(/Saved\. Recalculating GA_GA-001 from TY2021/)).toBeInTheDocument();
    // Said on screen, because it is the question somebody will ask next.
    expect(screen.getByText(/Targeting book is unaffected/)).toBeInTheDocument();
  });

  it('a base the run took from a saved choice says so, and can be cleared', async () => {
    const saved = grid();
    saved.items = saved.items.map((row) => ({ ...row, base_year_source: 'override' }));
    api.fetchClientUnits.mockResolvedValue(saved);
    api.saveBaseYear.mockResolvedValue({ recorded: true, recalculation: 'started' });
    render(<TrendGridView scope={scope} scopeOptions={scopeOptions} />);
    const picker = await screen.findByRole('combobox', { name: 'Base year for GA_GA-001' });
    expect([...picker.options][0].textContent).toBe('TY2020 (saved)');
    expect(screen.getByText(/was/).closest('p')).toHaveTextContent('saved for this location');
    await userEvent.click(screen.getByRole('button', { name: 'Clear the saved base year' }));
    await waitFor(() => expect(api.saveBaseYear).toHaveBeenCalledWith(
      2001, 'GA_GA-001', expect.objectContaining({ baseYear: null }),
    ));
  });

  it('going back to the run\u2019s own year removes the override', async () => {
    api.fetchClientUnits.mockResolvedValue(grid());
    api.fetchUnitRebase.mockResolvedValue(REBASE);
    render(<TrendGridView scope={scope} scopeOptions={scopeOptions} />);
    await userEvent.selectOptions(await screen.findByRole('combobox', { name: 'Base year for GA_GA-001' }), '2021');
    await userEvent.click(await screen.findByRole('button', { name: 'Back to TY2020' }));
    await waitFor(() => expect(screen.queryByRole('status')).not.toBeInTheDocument());
    expect(screen.getByRole('combobox', { name: 'Base year for GA_GA-001' })).toHaveValue('2020');
  });
});
