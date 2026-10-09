import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import UnitPage from './UnitPage.jsx';

vi.mock('../api.js', async () => {
  const actual = await vi.importActual('../api.js');
  return { ...actual, fetchClientUnit: vi.fn() };
});

const api = await import('../api.js');

const person = (n, counted = 1, over = {}) => ({
  record_token: `tok-${n}`,
  employee_id: `E${String(n).padStart(5, '0')}`,
  weight: 1,
  month_05: counted,
  ...over,
});

function payload(count, over = {}) {
  return {
    calculation_state: 'calculated',
    run: { run_id: '1ef66984739b4e22986ec57603fe8a7c', produced_at: '2026-09-01T10:00:00Z' },
    unit: { worksite_id: 'GA_GA-001', average_headcount: 25.92, base_year: 2020, status: 'qualified' },
    employees: Array.from({ length: count }, (_, i) => person(i + 1)),
    total: count,
    month_filter: { month_index: 5 },
    ...over,
  };
}

afterEach(() => vi.clearAllMocks());

const base = { clientId: 2001, unitId: 'GA_GA-001', year: 2023, clientName: 'Cascade' };

/** Sort, filters and the open tab all live in the URL, so the page needs one. */
const draw = (props = {}, entries = ['/']) => render(
  <MemoryRouter initialEntries={entries}><UnitPage {...base} {...props} /></MemoryRouter>,
);

const tab = (name) => screen.getByRole('tab', { name: new RegExp(name) });

describe('the month narrows the population rather than annotating it', () => {
  it('reports the people the statute counts in that month, not everyone at the location', async () => {
    // Cascade GA_GA-001 has 29 people across TY2023 and 25 in month 5. The
    // drawer this replaced returned all 29 under a month heading.
    api.fetchClientUnit.mockResolvedValue(payload(25));

    draw({ month: 5 });

    expect(await screen.findByRole('tab', { name: /Counted\s*25/ })).toBeInTheDocument();
    await waitFor(() => expect(api.fetchClientUnit).toHaveBeenCalledWith(
      2001, 'GA_GA-001', expect.objectContaining({ year: 2023, month: 5 }),
    ));
  });

  it('asks for the whole year when no month is in the URL', async () => {
    api.fetchClientUnit.mockResolvedValue(payload(29, { month_filter: { month_index: null } }));

    draw({ month: null });

    expect(await screen.findByRole('tab', { name: /Counted\s*29/ })).toBeInTheDocument();
    expect(api.fetchClientUnit).toHaveBeenCalledWith(
      2001, 'GA_GA-001', expect.objectContaining({ month: null }),
    );
  });
});

describe('the page states what it cannot show', () => {
  it('renders not_calculated as a statement, never as an empty table', async () => {
    api.fetchClientUnit.mockResolvedValue({
      calculation_state: 'not_calculated',
      message: 'Not assessed yet. It carries no figure — not a zero.',
      unit: null,
      employees: [],
    });

    draw({ month: 5 });

    expect(await screen.findByRole('heading', { name: /Awaiting the next run/i })).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('names the run that produced the figures', async () => {
    api.fetchClientUnit.mockResolvedValue(payload(25));
    draw({ month: 5 });
    expect(await screen.findByText(/1ef66984739b/)).toBeInTheDocument();
  });
});

describe('the cohort the band announces is actually on the page', () => {
  // The band said "8 more within 5 hrs" and the table listed only the people
  // who counted. The eight most actionable rows in the product were invisible.
  const withNear = payload(20, {
    thresholds: { min_weekly_hours: 35, min_weekly_wages: 636, resolved: true },
    near_threshold: [
      { record_token: 'n1', employee_id: 'E9001', avg_weekly_hours: 34.29, avg_weekly_wages: 1034.29 },
      { record_token: 'n2', employee_id: 'E9002', avg_weekly_hours: 31.01, avg_weekly_wages: 1032.66 },
      { record_token: 'n3', employee_id: 'E9003', avg_weekly_hours: 12.5, avg_weekly_wages: 400 },
    ],
  });

  it('renders the near-threshold rows, closest first', async () => {
    api.fetchClientUnit.mockResolvedValue(withNear);
    draw({ month: 5 });

    await userEvent.click(await screen.findByRole('tab', { name: /Near the floor/ }));
    const rows = within(document.getElementById('unit-near')).getAllByRole('row').slice(1);
    expect(rows.map((r) => within(r).getAllByRole('cell')[0].textContent))
      .toEqual(['E9001', 'E9002', 'E9003']);
  });

  it('shows how far short each one is, from the rule pack floor', async () => {
    api.fetchClientUnit.mockResolvedValue(withNear);
    draw({ month: 5 });

    await userEvent.click(await screen.findByRole('tab', { name: /Near the floor/ }));
    // 35.0 - 34.29. The demo moment: under three quarters of an hour.
    expect(screen.getByText('0.71 hrs')).toBeInTheDocument();
    expect(screen.getByText('3.99 hrs')).toBeInTheDocument();
  });

  it('says which band it applied and how many fall inside it', async () => {
    api.fetchClientUnit.mockResolvedValue(withNear);
    draw({ month: 5 });

    expect(await screen.findByText(/Within 5 hrs of the floor/)).toBeInTheDocument();
    expect(screen.getByText('3 ineligible in all')).toBeInTheDocument();
  });

  it('keeps them out of the counted table, which would claim they counted', async () => {
    api.fetchClientUnit.mockResolvedValue(withNear);
    draw({ month: 5 });

    await screen.findByRole('table');
    expect(within(document.getElementById('unit-counted')).queryByText('E9001'))
      .not.toBeInTheDocument();
  });
});

describe('"how many more hours a week would Sally need to work?"', () => {
  // The partner asks this by name. It is NOT the same number as "short by" whenever
  // the wage floor is the binding one — and the person it differs for is the
  // one the hours gap alone reports as nearly fine.
  const withLever = payload(20, {
    thresholds: { min_weekly_hours: 35, min_weekly_wages: 636, resolved: true },
    near_threshold: [
      {
        record_token: 'n1', employee_id: 'E9001',
        avg_weekly_hours: 34.29, avg_weekly_wages: 1034.29,
        additional_weekly_hours: 0.71, projected_weekly_hours: 35,
        failure_mode: 'hours_only', exceeds_plausible_week: false,
        hourly_rate_to_qualify: null,
      },
      {
        // Clears the hours floor, fails the wage floor at a low rate. The
        // hours gap says 0; the lever says 20.
        record_token: 'n2', employee_id: 'E9002',
        avg_weekly_hours: 36, avg_weekly_wages: 288,
        additional_weekly_hours: 20, projected_weekly_hours: 56,
        failure_mode: 'wages_only', exceeds_plausible_week: false,
        hourly_rate_to_qualify: 17.67,
      },
      {
        record_token: 'n3', employee_id: 'E9003',
        avg_weekly_hours: 12.5, avg_weekly_wages: 100,
        additional_weekly_hours: 67.5, projected_weekly_hours: 80,
        failure_mode: 'both', exceeds_plausible_week: true,
        hourly_rate_to_qualify: null,
      },
    ],
  });

  async function openNear() {
    api.fetchClientUnit.mockResolvedValue(withLever);
    draw({ month: 5 });
    await userEvent.click(await screen.findByRole('tab', { name: /Near the floor/ }));
    return within(document.getElementById('unit-near'));
  }

  it('states the additional hours per employee', async () => {
    const near = await openNear();
    // Twice on the row for E9001: the hours gap and the lever agree when the
    // hours floor is the only one failing, which is most people.
    const row = near.getByRole('row', { name: /E9001/ });
    expect(within(row).getAllByRole('cell').at(-3).textContent).toBe('0.71 hrs');
  });

  it('exceeds the visible hours gap when the wage floor is the binding one', async () => {
    // E9002 is ABOVE the hours floor, so "short by" reads as no gap at all.
    // Showing only that tells this person they are fine.
    const near = await openNear();
    const row = near.getByRole('row', { name: /E9002/ });
    expect(within(row).getByText('20.00 hrs')).toBeInTheDocument();
  });

  it('marks a lever that needs a week nobody works', async () => {
    const near = await openNear();
    const row = near.getByRole('row', { name: /E9003/ });
    const cell = within(row).getAllByRole('cell').at(-3);
    expect(cell.textContent).toContain('67.50 hrs');
    expect(cell.querySelector('sup')).not.toBeNull();
  });

  it('shows no per-person dollar figure', async () => {
    // A location's credit turns on its job count against a threshold, so the
    // marginal employee is worth the whole tranche or nothing. Neither can be
    // attributed to a row, so the column says the hours.
    const near = await openNear();
    const row = near.getByRole('row', { name: /E9002/ });
    const cell = within(row).getAllByRole('cell').at(-3);
    expect(cell.textContent).not.toMatch(/\$/);
  });

  it('marks the wage floor from the comparison, not from the failure mode', async () => {
    // Somebody can fail BOTH floors and still have the hours gap bind: 31.23
    // hrs at $620.90 needs 3.77 more hours for the schedule and 0.76 for the
    // pay. Marking them would claim the wage floor moved a number it did not.
    api.fetchClientUnit.mockResolvedValue(payload(20, {
      thresholds: { min_weekly_hours: 35, min_weekly_wages: 636, resolved: true },
      near_threshold: [{
        record_token: 'n5', employee_id: 'E9005',
        avg_weekly_hours: 31.23, avg_weekly_wages: 620.90,
        additional_weekly_hours: 3.77, projected_weekly_hours: 35,
        failure_mode: 'both', exceeds_plausible_week: false,
      }],
    }));
    draw({ month: 5 });
    await userEvent.click(await screen.findByRole('tab', { name: /Near the floor/ }));
    const row = within(document.getElementById('unit-near')).getByRole('row', { name: /E9005/ });
    const cell = within(row).getAllByRole('cell').at(-3);
    expect(cell.textContent).toBe('3.77 hrs');
    expect(cell.querySelector('sup')).toBeNull();
  });

  it('does not report a shortfall for somebody over the hours floor', async () => {
    // The dominant case on the reference client: 192 of 200 near-threshold
    // employees at one Candle Bottle unit clear 35 hours and fail on wages.
    // `floor - hours` is NEGATIVE for them, and "short by -1.33 hrs" in an
    // amber pill reads as a shortfall that is not there.
    api.fetchClientUnit.mockResolvedValue(payload(20, {
      thresholds: { min_weekly_hours: 35, min_weekly_wages: 636, resolved: true },
      near_threshold: [{
        record_token: 'n6', employee_id: 'E9006',
        avg_weekly_hours: 36.33, avg_weekly_wages: 553.23,
        additional_weekly_hours: 5.44, projected_weekly_hours: 41.77,
        failure_mode: 'wages_only', exceeds_plausible_week: false,
        hourly_rate_to_qualify: 17.51,
      }],
    }));
    draw({ month: 5 });
    await userEvent.click(await screen.findByRole('tab', { name: /Near the floor/ }));
    const row = within(document.getElementById('unit-near')).getByRole('row', { name: /E9006/ });
    const cells = within(row).getAllByRole('cell');
    expect(cells.at(-4).textContent).toBe('over');
    expect(cells.at(-4).textContent).not.toMatch(/-/);
    // The real distance, and it is marked as wage-driven.
    expect(cells.at(-3).textContent).toContain('5.44 hrs');
    expect(cells.at(-3).querySelector('sup')).not.toBeNull();
  });

  it('says nothing rather than zero when there is no rate to price hours at', async () => {
    api.fetchClientUnit.mockResolvedValue(payload(20, {
      thresholds: { min_weekly_hours: 35, min_weekly_wages: 636, resolved: true },
      near_threshold: [{
        record_token: 'n4', employee_id: 'E9004',
        avg_weekly_hours: 0, avg_weekly_wages: 0,
        additional_weekly_hours: null, projected_weekly_hours: null,
        failure_mode: 'both', exceeds_plausible_week: false,
      }],
    }));
    draw({ month: 5 });
    await userEvent.click(await screen.findByRole('tab', { name: /Near the floor/ }));
    const row = within(document.getElementById('unit-near')).getByRole('row', { name: /E9004/ });
    expect(within(row).getAllByRole('cell').at(-3).textContent).toBe('—');
  });
});

describe('the two cohorts are peers behind one tab strip', () => {
  const withNear = payload(4, {
    thresholds: { min_weekly_hours: 35, min_weekly_wages: 636, resolved: true },
    near_threshold: [
      { record_token: 'n1', employee_id: 'E9001', avg_weekly_hours: 34.29, avg_weekly_wages: 1034.29 },
    ],
  });

  it('carries the count in the label, so the tab says whether to click it', async () => {
    api.fetchClientUnit.mockResolvedValue(withNear);
    draw({ month: 5 });

    await screen.findByRole('table');
    expect(tab('Counted')).toHaveTextContent('4');
    expect(tab('Near the floor')).toHaveTextContent('1');
  });

  it('opens on the counted list, which is what the credit is computed from', async () => {
    api.fetchClientUnit.mockResolvedValue(withNear);
    draw({ month: 5 });

    await screen.findByRole('table');
    expect(tab('Counted')).toHaveAttribute('aria-selected', 'true');
    expect(document.getElementById('unit-near')).toBeNull();
  });

  it('shows only one grid at a time, which is the point of tabbing them', async () => {
    api.fetchClientUnit.mockResolvedValue(withNear);
    draw({ month: 5 });

    await userEvent.click(await screen.findByRole('tab', { name: /Near the floor/ }));
    expect(document.getElementById('unit-counted')).toBeNull();
    expect(document.getElementById('unit-near')).not.toBeNull();
  });

  it('restores the open tab from the URL, so a shared link lands where it was', async () => {
    api.fetchClientUnit.mockResolvedValue(withNear);
    draw({ month: 5 }, ['/?tab=near']);

    expect(await screen.findByRole('tab', { name: /Near the floor/ }))
      .toHaveAttribute('aria-selected', 'true');
  });
});

describe('the row carries enough to judge it without opening it', () => {
  const detailed = payload(0, {
    thresholds: { min_weekly_hours: 35, min_weekly_wages: 636, resolved: true },
    employees: [
      person(1, 1, {
        weeks_worked: 6, total_hours: 240, avg_weekly_hours: 40, avg_weekly_wages: 800,
        first_pps: '2023-01-02', last_ppe: '2023-02-12',
      }),
      person(2, 1, {
        weeks_worked: 52, total_hours: 2080, avg_weekly_hours: 40, avg_weekly_wages: 800,
        first_pps: '2023-01-02', last_ppe: '2023-12-31',
      }),
    ],
  });

  it('separates 40 hours over six weeks from 40 over fifty-two', async () => {
    // Identical weekly averages. Without the denominator the two rows render
    // the same, which is why weeks_worked earns a column.
    api.fetchClientUnit.mockResolvedValue(detailed);
    draw({ month: null });

    const rows = within(await screen.findByRole('table')).getAllByRole('row').slice(1);
    expect(within(rows[0]).getAllByRole('cell')[1]).toHaveTextContent('6');
    expect(within(rows[1]).getAllByRole('cell')[1]).toHaveTextContent('52');
  });

  it('says where in the year those weeks fell', async () => {
    api.fetchClientUnit.mockResolvedValue(detailed);
    draw({ month: null });

    expect(await screen.findByText('2 Jan 23 – 12 Feb 23')).toBeInTheDocument();
    expect(screen.getByText('2 Jan 23 – 31 Dec 23')).toBeInTheDocument();
  });

  it('hides Share when every row is a whole employee', async () => {
    // A column reading 1.00 on every row costs the same width as one that says
    // something.
    api.fetchClientUnit.mockResolvedValue(detailed);
    draw({ month: null });

    await screen.findByRole('table');
    expect(screen.queryByText('Share')).not.toBeInTheDocument();
  });

  it('shows Share as soon as one employee is split across locations', async () => {
    api.fetchClientUnit.mockResolvedValue(payload(0, {
      employees: [person(1, 1, { weight: 0.5 }), person(2, 1, { weight: 1 })],
    }));
    draw({ month: null });

    expect(await screen.findByText('Share')).toBeInTheDocument();
  });
});

describe('filtering is pushed to the warehouse, not applied to what came back', () => {
  const many = payload(3, {
    total_unfiltered: 29,
    filters_applied: { avg_weekly_hours: '>=35' },
    thresholds: { min_weekly_hours: 35, min_weekly_wages: 636, resolved: true },
  });

  it('sends the filter as a query rather than fetching everyone', async () => {
    api.fetchClientUnit.mockResolvedValue(many);
    draw({ month: null }, ['/?emp_f=avg_weekly_hours:>=35']);

    await waitFor(() => expect(api.fetchClientUnit).toHaveBeenCalledWith(
      2001, 'GA_GA-001', expect.objectContaining({ filter: 'avg_weekly_hours:>=35' }),
    ));
  });

  it('states what it is hiding, because a forgotten filter is a wrong total', async () => {
    api.fetchClientUnit.mockResolvedValue(many);
    draw({ month: null }, ['/?emp_f=avg_weekly_hours:>=35']);

    expect(await screen.findByText('Showing 3 of 29 employees')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Clear all/ })).toBeInTheDocument();
  });

  it('keeps the location figures on the unfiltered population', async () => {
    // The count is a claim about the location, not about what the reader
    // narrowed to: 3 rows on screen, 29 employees counted.
    api.fetchClientUnit.mockResolvedValue(many);
    draw({ month: null }, ['/?emp_f=avg_weekly_hours:>=35']);

    expect(await screen.findByRole('tab', { name: /Counted\s*29/ })).toBeInTheDocument();
    const card = screen.getByText('Counted this year').closest('.tcc-stat');
    expect(within(card).getByText('29')).toBeInTheDocument();
  });

  it('filters the two cohorts independently', async () => {
    api.fetchClientUnit.mockResolvedValue(many);
    draw({ month: null }, ['/?emp_f=weeks_worked:>=10&near_f=avg_weekly_hours:>=30']);

    await waitFor(() => expect(api.fetchClientUnit).toHaveBeenCalledWith(
      2001, 'GA_GA-001', expect.objectContaining({
        filter: 'weeks_worked:>=10', nearFilter: 'avg_weekly_hours:>=30',
      }),
    ));
  });

  it('survives a refresh, because sort and filter are both in the URL', async () => {
    api.fetchClientUnit.mockResolvedValue(many);
    draw({ month: null }, ['/?emp_f=weeks_worked:>=10&esort=weeks_worked&eorder=asc']);

    await waitFor(() => expect(api.fetchClientUnit).toHaveBeenCalledWith(
      2001, 'GA_GA-001', expect.objectContaining({
        filter: 'weeks_worked:>=10', sort: 'weeks_worked', order: 'asc',
      }),
    ));
  });

  it('does not pass a term the grammar cannot read', async () => {
    // A control that looks live and filters nothing is how a reader trusts a
    // wrong number, so an unparseable term is dropped before the request.
    api.fetchClientUnit.mockResolvedValue(payload(29));
    draw({ month: null }, ['/?emp_f=weeks_worked:banana']);

    await waitFor(() => expect(api.fetchClientUnit).toHaveBeenCalledWith(
      2001, 'GA_GA-001', expect.objectContaining({ filter: '' }),
    ));
    expect(screen.queryByText(/^Showing/)).not.toBeInTheDocument();
  });
});

describe('effort is shown against a floor the API supplied', () => {
  it('lists hours and wages rather than a column that is 1 on every row', async () => {
    api.fetchClientUnit.mockResolvedValue(payload(2, {
      thresholds: { min_weekly_hours: 35, min_weekly_wages: 636, resolved: true },
    }));
    draw({ month: 5 });

    await screen.findByRole('table');
    const counted = document.getElementById('unit-counted');
    // Anchored: the column's filter toggle is labelled "Filter Avg weekly hrs"
    // and an unanchored pattern matches both controls.
    expect(within(counted).getByRole('button', { name: /^Avg weekly hrs/ })).toBeInTheDocument();
    expect(within(counted).getByRole('button', { name: /^Avg weekly wages/ })).toBeInTheDocument();
  });

  it('names the floor from the payload, never a hardcoded 35', async () => {
    api.fetchClientUnit.mockResolvedValue(payload(1, {
      thresholds: { min_weekly_hours: 30, min_weekly_wages: 500, resolved: true },
      near_threshold: [],
    }));
    draw({ month: 5 });
    expect(await screen.findByText(/floor 30 hrs/)).toBeInTheDocument();
  });
});

describe('a labelled card with no value is worse than no card', () => {
  it('omits the base year rather than printing TY em-dash', async () => {
    api.fetchClientUnit.mockResolvedValue(payload(1, {
      unit: { worksite_id: 'GA_GA-001', average_headcount: 25.92, base_year: null, status: 'qualified' },
    }));
    draw({ month: 5 });

    await screen.findByRole('table');
    expect(screen.queryByText('Base year')).not.toBeInTheDocument();
    expect(screen.queryByText('TY—')).not.toBeInTheDocument();
  });
});

describe('an employee is opened by token', () => {
  it('never puts the employee id in the handle it hands upward', async () => {
    api.fetchClientUnit.mockResolvedValue(payload(1));
    const onOpenEmployee = vi.fn();

    draw({ month: 5, onOpenEmployee });
    await userEvent.click(await screen.findByRole('button', { name: /Open the walk/ }));

    expect(onOpenEmployee).toHaveBeenCalledWith('tok-1');
    expect(onOpenEmployee).not.toHaveBeenCalledWith(expect.stringContaining('E00001'));
  });
});

describe('a slow read cannot paint under the wrong unit', () => {
  it('drops a payload that belongs to a unit the viewer has left', async () => {
    let release;
    api.fetchClientUnit
      .mockImplementationOnce(() => new Promise((resolve) => { release = () => resolve(payload(25)); }))
      .mockResolvedValue(payload(3));

    const { rerender } = render(
      <MemoryRouter><UnitPage {...base} month={5} /></MemoryRouter>,
    );
    rerender(<MemoryRouter><UnitPage {...base} unitId="GA_GA-002" month={5} /></MemoryRouter>);
    release();

    expect(await screen.findByRole('tab', { name: /Counted\s*3/ })).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: /Counted\s*25/ })).not.toBeInTheDocument();
  });
});

describe('near-the-floor people go into the What-if stack (29 Sep)', () => {
  const open = (hours) => ({ state: 'open', additional_weekly_hours: hours, remaining_pay_periods: 8 });
  const withRest = payload(3, {
    year: 2026,
    thresholds: { min_weekly_hours: 35, min_weekly_wages: 680, resolved: true },
    near_threshold: [
      { record_token: 'n1', employee_id: 'E9001', avg_weekly_hours: 34.29, avg_weekly_wages: 1034, rest_of_year: open(1.5) },
      { record_token: 'n2', employee_id: 'E9002', avg_weekly_hours: 31.01, avg_weekly_wages: 900, rest_of_year: open(4) },
      { record_token: 'n3', employee_id: 'E9003', avg_weekly_hours: 36, avg_weekly_wages: 600, rest_of_year: { state: 'on_pace' } },
    ],
  });

  beforeEach(async () => {
    const store = await import('../lib/whatIfStack.js');
    const data = new Map();
    store.setStackStorage({ getItem: (k) => data.get(k) ?? null, setItem: (k, v) => data.set(k, v), removeItem: (k) => data.delete(k) });
  });

  it('adds one at a time, or ticks several; a person on pace offers no lever', async () => {
    const { readStack } = await import('../lib/whatIfStack.js');
    api.fetchClientUnit.mockResolvedValue(withRest);
    draw({ month: 7, year: 2026 }, ['/?tab=near']);

    await userEvent.click(await screen.findByRole('button', { name: 'Add E9001 to the What-if stack' }));
    expect(readStack({ clientId: 2001, taxYear: 2026, method: 'min_max' })).toEqual([{ token: 'n1', hours: 1.5, raise: 0 }]);
    expect(screen.getByRole('button', { name: 'Remove E9001 from the What-if stack' })).toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: 'Select E9003' })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('checkbox', { name: 'Select every row that can be added' }));
    await userEvent.click(screen.getByRole('button', { name: /Add selected \(1\)/ }));
    expect(readStack({ clientId: 2001, taxYear: 2026, method: 'min_max' }).map((e) => e.token)).toEqual(['n1', 'n2']);
    expect(screen.getByText(/in the What-if stack/)).toHaveTextContent('2 in the What-if stack');
  });

  it('a closed year offers no stack at all', async () => {
    api.fetchClientUnit.mockResolvedValue(payload(3, {
      thresholds: { min_weekly_hours: 35, min_weekly_wages: 636, resolved: true },
      near_threshold: [{ record_token: 'n1', employee_id: 'E9001', avg_weekly_hours: 34, avg_weekly_wages: 900 }],
    }));
    draw({ month: 5 }, ['/?tab=near']);
    await screen.findByText('E9001');
    expect(screen.queryByRole('toolbar', { name: 'What-if stack' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Add E9001/ })).not.toBeInTheDocument();
  });
});
