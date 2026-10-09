/**
 * Near the Line: render smoke tests.
 *
 * The value of this view is an *instruction*, not a count, and there are two
 * ways to get the instruction wrong that a count-only test would not catch:
 *
 * 1. Collapsing the failure modes. "Work them more hours" is wrong advice for
 *    somebody already at 40 hours who is simply paid too little.
 * 2. Quoting hours to an employee paid below the threshold rate, where the wage
 *    floor binds harder and the honest lever is a raise.
 *
 * These tests pin both, plus the scope-freshness rule: a payload fetched under
 * one client must never render under another's heading.
 */
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ProximityView from './ProximityView.jsx';
import { PORTFOLIO } from '../lib/scopeDimension.js';
import * as api from '../api.js';

const SCOPE_OPTIONS = {
  clients: [
    { account_id: 1001, name: 'Candle Bottle', synthetic: false },
    { account_id: 2003, name: 'Ironbridge Logistics', synthetic: true },
  ],
  // Jurisdiction is derived from the programme, so the fixture must carry the
  // programme list. An earlier version of this file put `jurisdiction: 'GA'`
  // straight onto the scope object — a field `reconcileScope` never sets — and
  // every test passed against a shape the app does not produce.
  programs: [
    {
      program_code: 'GA_JTC',
      name: 'Georgia Jobs Tax Credit',
      jurisdiction: { level: 'state', code: 'GA', name: 'Georgia' },
      authored_years: [2022, 2023],
      calculable: true,
    },
    {
      program_code: 'TN_JTC',
      name: 'Tennessee Job Tax Credit',
      jurisdiction: { level: 'state', code: 'TN', name: 'Tennessee' },
      authored_years: [],
      calculable: false,
    },
  ],
};

const scope = (overrides = {}) => ({
  clientId: 1001, programCode: 'GA_JTC', year: 2023, ...overrides,
});

const PAYLOAD = {
  floors: {
    program_code: 'GA_JTC',
    tax_year: 2023,
    minimum_average_weekly_hours: 35.0,
    minimum_average_weekly_wages_usd: 636.0,
    threshold_hourly_rate: 18.17,
    source: 'rules/ga_jtc/2023.json',
  },
  band_weekly_hours: 5,
  evaluated: 10236,
  eligible: 539,
  ineligible: 9697,
  failure_modes: { hours_only: 27, wages_only: 12, both: 9658 },
  within_band: 3,
  rate_limited_in_band: 1,
  exceeds_plausible_week_in_band: 0,
  returned: 3,
  bands: [
    { within_weekly_hours: 1, employees: 1, plausible: 1 },
    { within_weekly_hours: 2, employees: 2, plausible: 2 },
    { within_weekly_hours: 5, employees: 3, plausible: 3 },
    { within_weekly_hours: 10, employees: 8, plausible: 7 },
  ],
  cohort: [
    {
      employee_id: 'E00015', weeks_worked: 51.86, avg_weekly_hours: 34.94,
      avg_weekly_wages: 850.83, eligible: false, failed: ['hours'],
      failure_mode: 'hours_only', hours_gap_per_week: 0.06, wages_gap_per_week: 0,
      implied_hourly_rate: 24.35, threshold_hourly_rate: 18.17, rate_limited: false,
      additional_weekly_hours: 0.06, projected_weekly_hours: 35.0,
      exceeds_plausible_week: false, hourly_rate_to_qualify: null,
    },
    {
      employee_id: 'E00204', weeks_worked: 51.86, avg_weekly_hours: 40.0,
      avg_weekly_wages: 600.0, eligible: false, failed: ['wages'],
      failure_mode: 'wages_only', hours_gap_per_week: 0, wages_gap_per_week: 36.0,
      implied_hourly_rate: 15.0, threshold_hourly_rate: 18.17, rate_limited: true,
      additional_weekly_hours: 2.4, projected_weekly_hours: 42.4,
      exceeds_plausible_week: true, hourly_rate_to_qualify: 15.9,
    },
    {
      employee_id: 'E00891', weeks_worked: 51.86, avg_weekly_hours: 20.0,
      avg_weekly_wages: 240.0, eligible: false, failed: ['hours', 'wages'],
      failure_mode: 'both', hours_gap_per_week: 15.0, wages_gap_per_week: 396.0,
      implied_hourly_rate: 12.0, threshold_hourly_rate: 18.17, rate_limited: true,
      additional_weekly_hours: 33.0, projected_weekly_hours: 53.0,
      exceeds_plausible_week: true, hourly_rate_to_qualify: null,
    },
  ],
  method_note: 'Additional hours are priced at each employee\u2019s own implied hourly rate.',
  state: 'GA', program_code: 'GA_JTC', tax_year: 2023, method: 'min_max', account_id: 1001,
};

let spy;

beforeEach(() => {
  spy = vi.spyOn(api, 'fetchEmployeeProximity').mockResolvedValue(PAYLOAD);
});

afterEach(() => { vi.restoreAllMocks(); });

describe('Near the Line', () => {
  it('asks for one programme rather than crashing when several are in scope', () => {
    // ALL_PROGRAMS derives many jurisdictions; a cohort spanning two statutes
    // would rank employees against different rulers.
    render(<ProximityView scope={scope({ programCode: 'all' })} scopeOptions={SCOPE_OPTIONS} />);
    expect(screen.getByText(/select a single program/i)).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });

  it('derives the jurisdiction from the programme rather than reading it off scope', async () => {
    render(<ProximityView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(spy).toHaveBeenLastCalledWith(expect.objectContaining({ state: 'GA' }));
  });

  it('leads with how many are within reach, not with how many are ineligible', async () => {
    const { container } = render(<ProximityView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);
    const lead = await screen.findByText('3 within reach');
    // First thing the summary says, before any count of the ineligible.
    expect(container.querySelector('.prox-summary').firstElementChild).toBe(lead);
  });

  it('counts the three failure modes separately', async () => {
    const { container } = render(
      <ProximityView scope={scope()} scopeOptions={SCOPE_OPTIONS} />,
    );
    await screen.findByText('3 within reach');
    // Scoped to the summary on purpose: "Hours only" is also a cell label in
    // the table below, so an unscoped query matches twice and would otherwise
    // pass for the wrong reason.
    const summary = container.querySelector('.prox-summary');
    for (const [mode, value] of [['hours_only', '27'], ['wages_only', '12'], ['both', '9,658']]) {
      expect(within(summary.querySelector(`.prox-summary-mode.${mode}`)).getByText(value)).toBeInTheDocument();
    }
  });

  it('states the statutory floors and where they were resolved from', async () => {
    render(<ProximityView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);
    const floors = await screen.findByText(/requires/i);
    expect(within(floors).getByText('35 hrs/week')).toBeInTheDocument();
    expect(within(floors).getByText('$636/week')).toBeInTheDocument();
    expect(within(floors).getByText('rules/ga_jtc/2023.json')).toBeInTheDocument();
  });

  it('keeps the cents on an hourly rate, because the threshold has them', async () => {
    render(<ProximityView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);
    const floors = await screen.findByText(/requires/i);
    // $18.17, not "$18" — an employee on $18.10 is on the wrong side of it.
    expect(within(floors).getByText('$18.17/hr')).toBeInTheDocument();
  });

  it('gives a plain hours instruction to an employee paid above the threshold rate', async () => {
    render(<ProximityView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);
    const row = (await screen.findByText('E00015')).closest('tr');
    expect(within(row).getByText('+0.06h/wk')).toBeInTheDocument();
    expect(within(row).queryByText(/raise is the better lever/i)).not.toBeInTheDocument();
  });

  it('tells a rate-limited employee that a raise is the lever, not more hours', async () => {
    render(<ProximityView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);
    const row = (await screen.findByText('E00204')).closest('tr');
    expect(within(row).getByText(/raise is the better lever/i)).toBeInTheDocument();
    expect(within(row).getByText(/\$15\.90\/hr qualifies at today's hours/i)).toBeInTheDocument();
  });

  it('shows each failing test\u2019s own gap rather than one blended number', async () => {
    render(<ProximityView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);
    const row = (await screen.findByText('E00891')).closest('tr');
    expect(within(row).getByText(/−15.00h/)).toBeInTheDocument();
    expect(within(row).getByText(/−\$396/)).toBeInTheDocument();
  });

  it('refetches when the band changes and passes the new band through', async () => {
    const user = userEvent.setup();
    render(<ProximityView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);
    await screen.findByText('3 within reach');
    // One control for the band: the chips, each carrying its count.
    const band = within(screen.getByRole('group', { name: /within/i })).getByRole('button', { name: /^2h/ });
    expect(band).toHaveTextContent('2');
    await user.click(band);
    await waitFor(() => {
      expect(spy).toHaveBeenLastCalledWith(expect.objectContaining({ within: 2 }));
    });
  });

  it('refetches when the method changes', async () => {
    const user = userEvent.setup();
    render(<ProximityView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);
    await screen.findByText('3 within reach');
    await user.selectOptions(screen.getByLabelText(/method/i), 'pay_period');
    await waitFor(() => {
      expect(spy).toHaveBeenLastCalledWith(expect.objectContaining({ method: 'pay_period' }));
    });
  });

  it('asks nothing at portfolio scope, and says why', async () => {
    // This used to send `accountId: null`, which the backend answered from the
    // CONFIGURED TENANT — so account 1001's employees rendered under the
    // heading "All accounts". The cohort is read from one client's run: its
    // statute, its fiscal window, its recorded verdicts. There is no portfolio
    // version of it, and inventing one from whichever tenant is configured is
    // the mislabelling this component's own key-guard exists to prevent.
    render(<ProximityView scope={scope({ clientId: PORTFOLIO })} scopeOptions={SCOPE_OPTIONS} />);
    expect(
      await screen.findByText(/Select one client to see who is near the line/),
    ).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });

  it('never renders one client\u2019s payload under another client\u2019s heading', async () => {
    // The B3 bug: switching client showed the PREVIOUS client's figures for the
    // ~55s of a cold Fabric read. The in-flight cancel flag does not cover this
    // — the first request already committed. What must not happen is the old
    // payload staying on screen under the new heading while the new one loads.
    const resolvers = [];
    spy.mockImplementation((args) => new Promise((res) => {
      resolvers.push(() => res({ ...PAYLOAD, account_id: args.accountId }));
    }));

    const { rerender } = render(
      <ProximityView scope={scope({ clientId: 1001 })} scopeOptions={SCOPE_OPTIONS} />,
    );
    await waitFor(() => expect(resolvers).toHaveLength(1));
    resolvers[0]();
    // Client 1001's cohort is on screen and committed.
    expect(await screen.findByText('E00015')).toBeInTheDocument();

    // Now move to 2003. Its request is in flight and has NOT resolved.
    rerender(<ProximityView scope={scope({ clientId: 2003 })} scopeOptions={SCOPE_OPTIONS} />);
    await waitFor(() => expect(resolvers).toHaveLength(2));

    expect(screen.getByText(/Ironbridge Logistics/)).toBeInTheDocument();
    expect(screen.queryByText('E00015')).not.toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('surfaces a backend refusal instead of rendering an empty table', async () => {
    spy.mockRejectedValue(new Error('GA_JTC is not year-scoped for 2019'));
    render(<ProximityView scope={scope({ year: 2019 })} scopeOptions={SCOPE_OPTIONS} />);
    expect(await screen.findByText(/not year-scoped for 2019/i)).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('says nobody is close rather than showing a bare empty table', async () => {
    spy.mockResolvedValue({ ...PAYLOAD, cohort: [], within_band: 0, returned: 0 });
    render(<ProximityView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);
    expect(await screen.findByText(/nobody is within 5 hours a week/i)).toBeInTheDocument();
  });
});


describe('the rest of the year (WI-19), and the What-if stack', () => {
  const stackOf = (tokens = [], year = 2023) => ({
    tokens: new Set(tokens), year, method: 'min_max', onAdd: vi.fn(), onRemove: vi.fn(), onOpen: vi.fn(),
  });
  const withRest = (rows) => ({
    ...PAYLOAD,
    rest_of_year_as_of: '2023-08-31',
    cohort: PAYLOAD.cohort.map((row, i) => ({ ...row, record_token: `tok${i}`, rest_of_year: rows[i] })),
  });
  const REST = [
    { state: 'open', additional_weekly_hours: 2.87, remaining_pay_periods: 9, rate_limited: false, exceeds_plausible_week: false },
    { state: 'open', additional_weekly_hours: 6.1, remaining_pay_periods: 9, rate_limited: true, hourly_rate_to_qualify: 17.2 },
    { state: 'on_pace', pace_weekly_hours: 35.4 },
  ];

  it('asks for it only where the question is asked at the checkpoint', async () => {
    render(<ProximityView scope={scope()} scopeOptions={SCOPE_OPTIONS} embedded />);
    await waitFor(() => expect(spy).toHaveBeenLastCalledWith(expect.objectContaining({ restOfYear: true })));
  });

  it('says it the way the partner does, beside the full-year gap', async () => {
    spy.mockResolvedValue(withRest(REST));
    render(<ProximityView scope={scope()} scopeOptions={SCOPE_OPTIONS} embedded stack={stackOf()} />);
    expect(await screen.findByRole('columnheader', { name: /Full-year gap/ })).toBeInTheDocument();
    // The common count lives in the header, so each row stays on one line.
    expect(screen.getByRole('columnheader', { name: /Rest of year 9 pay periods from 2023-08-31/ })).toBeInTheDocument();
    expect(screen.getByText('+2.87h/wk')).toBeInTheDocument();
    expect(screen.getByTitle(/for the remaining 9 pay periods/)).toBeInTheDocument();
    // A rate-limited employee still gets "a raise", never an impossible week.
    expect(screen.getByText(/A raise is the better lever/)).toBeInTheDocument();
    expect(screen.getByText(/On pace at the checkpoint/)).toBeInTheDocument();
  });

  it('adds one open row at a time, by record token, pre-filled with what closes its gap', async () => {
    spy.mockResolvedValue(withRest(REST));
    const stack = stackOf();
    render(<ProximityView scope={scope()} scopeOptions={SCOPE_OPTIONS} embedded stack={stack} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Add E00015 to the What-if stack' }));
    expect(stack.onAdd).toHaveBeenCalledWith(
      [expect.objectContaining({ record_token: 'tok0', employee_id: 'E00015' })],
      { taxYear: 2023, method: 'min_max' },
    );
  });

  it('ticks several and adds them together; a row with no rest of the year cannot be ticked', async () => {
    spy.mockResolvedValue(withRest(REST));
    const stack = stackOf();
    render(<ProximityView scope={scope()} scopeOptions={SCOPE_OPTIONS} embedded stack={stack} />);
    const addSelected = await screen.findByRole('button', { name: /Add selected/ });
    expect(addSelected).toBeDisabled();
    expect(screen.queryByRole('checkbox', { name: 'Select E00891' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('checkbox', { name: 'Select every row that can be added' }));
    expect(addSelected).toHaveTextContent('Add selected (2) to What-if');
    await userEvent.click(addSelected);
    expect(stack.onAdd.mock.calls[0][0].map((r) => r.record_token)).toEqual(['tok0', 'tok1']);
  });

  it('shows who is already stacked, removes on a second click, and projects the stack', async () => {
    spy.mockResolvedValue(withRest(REST));
    const stack = stackOf(['tok0']);
    render(<ProximityView scope={scope()} scopeOptions={SCOPE_OPTIONS} embedded stack={stack} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Remove E00015 from the What-if stack' }));
    expect(stack.onRemove).toHaveBeenCalledWith('tok0');
    expect(screen.getByText(/in the What-if stack/)).toHaveTextContent('1 in the What-if stack');
    await userEvent.click(screen.getByRole('button', { name: /Project in What-if/ }));
    expect(stack.onOpen).toHaveBeenCalled();
  });

  it('a stack built for another year is not this list\u2019s', async () => {
    spy.mockResolvedValue(withRest(REST));
    render(<ProximityView scope={scope()} scopeOptions={SCOPE_OPTIONS} embedded stack={stackOf(['tok0'], 2026)} />);
    expect(await screen.findByRole('button', { name: 'Add E00015 to the What-if stack' })).toBeInTheDocument();
    expect(screen.getByText('The What-if stack is empty')).toBeInTheDocument();
  });

  it('names the location each person works at, with its designation', async () => {
    spy.mockResolvedValue({
      ...withRest(REST),
      cohort: withRest(REST).cohort.map((row, i) => (i === 0
        ? { ...row, worksite_id: 'GA_GA-013', worksites: ['GA_GA-001', 'GA_GA-013'], designation: 'T1 B40', tier: 1, tier_source: 'prototype' }
        : row)),
    });
    render(<ProximityView scope={scope()} scopeOptions={SCOPE_OPTIONS} embedded stack={stackOf()} />);
    expect(await screen.findByRole('columnheader', { name: /^Location/ })).toBeInTheDocument();
    expect(screen.getByText('GA_GA-013 +1')).toBeInTheDocument();
    expect(screen.getByText('T1 B40')).toBeInTheDocument();
  });

  it('offers no lever where there is no rest of the year to change', async () => {
    spy.mockResolvedValue(withRest(REST));
    render(<ProximityView scope={scope()} scopeOptions={SCOPE_OPTIONS} embedded stack={stackOf()} />);
    await screen.findByText(/On pace at the checkpoint/);
    expect(screen.queryByRole('button', { name: /E00891/ })).not.toBeInTheDocument();
  });
  it('sorts and filters by location, and "select all" takes only what is shown', async () => {
    // James, 29 Sep: line up the people one location needs, then stack them.
    const sites = ['GA_GA-013', 'GA_GA-001', 'GA_GA-013'];
    spy.mockResolvedValue({
      ...withRest(REST),
      cohort: withRest(REST).cohort.map((row, i) => ({
        ...row, worksite_id: sites[i], worksites: [sites[i]],
        rest_of_year: { state: 'open', additional_weekly_hours: 1 + i, remaining_pay_periods: 9 },
      })),
    });
    const stack = stackOf();
    render(<ProximityView scope={scope()} scopeOptions={SCOPE_OPTIONS} embedded stack={stack} />);

    await userEvent.click(await screen.findByRole('button', { name: /^Location/ }));
    const firstCells = () => screen.getAllByRole('row').slice(1).map((r) => within(r).getAllByRole('cell')[1].textContent);
    expect(firstCells()).toEqual(['E00204', 'E00015', 'E00891']);

    await userEvent.click(screen.getByRole('button', { name: 'Filter Location' }));
    await userEvent.click(screen.getByRole('checkbox', { name: 'GA_GA-013' }));
    expect(screen.getByText(/Showing 2 of 3 employees/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('checkbox', { name: 'Select every row that can be added' }));
    await userEvent.click(screen.getByRole('button', { name: /Add selected \(2\)/ }));
    expect(stack.onAdd.mock.calls[0][0].map((r) => r.employee_id)).toEqual(['E00015', 'E00891']);
  });
});