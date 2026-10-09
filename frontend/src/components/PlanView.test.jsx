/**
 * What-If: render smoke tests.
 *
 * A projection is still a statutory figure — somebody acts on it — so it runs
 * under the selected year's rules and declines an unauthored year rather than
 * borrowing a neighbour's.
 *
 * The portfolio half of this file is gone. "Who is closest to a threshold" is
 * now a PriorityBand on the book, covered by pageComposition.test.jsx.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { PlanLevers, planJurisdiction } from './PlanView.jsx';
import * as api from '../api.js';

const SCOPE_OPTIONS = {
  clients: [
    { account_id: 1001, name: 'Candle Bottle', synthetic: false },
    { account_id: 2003, name: 'Ironbridge Logistics', synthetic: true },
  ],
  programs: [
    {
      program_code: 'GA_JTC',
      name: 'Georgia Jobs Tax Credit',
      jurisdiction: { level: 'state', code: 'GA', name: 'Georgia' },
      authored_years: [2022, 2023],
      calculable: true,
    },
  ],
};

const scope = (overrides = {}) => ({
  clientId: 2003, programCode: 'GA_JTC', year: 2023, windowMode: false, ...overrides,
});

const SIMULATION = {
  detail: 'Added 5 full-time roles at the highest-hours pattern.',
  eligibility_floors: { min_weekly_hours: 35, min_weekly_wages: 636 },
  baseline: {
    average_headcount: 73.0, eligible_employee_count: 60,
    annual_credit_usd: 0, lifetime_credit_usd: 0,
  },
  projected: {
    average_headcount: 78.0, eligible_employee_count: 65,
    annual_credit_usd: 17500, lifetime_credit_usd: 87500,
  },
  delta: {
    average_headcount: 5.0, eligible_employee_count: 5,
    annual_credit_usd: 17500, lifetime_credit_usd: 87500,
  },
};

/**
 * Composed exactly as ClientPage composes it: the levers take a scope carrying
 * a derived jurisdiction, plus the client's display name. Keeping the shim here
 * means the tests exercise the real composition rather than a convenience
 * wrapper the app does not have.
 */
function PlanView({ scope: s, scopeOptions }) {
  const jurisdiction = planJurisdiction(s, scopeOptions);
  const name = (scopeOptions?.clients || [])
    .find((c) => c.account_id === s.clientId)?.name || `Account ${s.clientId}`;
  return <PlanLevers scope={{ ...s, jurisdiction }} clientName={name} />;
}

beforeEach(() => {
  vi.spyOn(api, 'simulateOneZero').mockResolvedValue(SIMULATION);
  vi.spyOn(api, 'fetchClientUnits').mockResolvedValue({ items: [], units: [] });
});

afterEach(() => vi.restoreAllMocks());

// ------------------------------------------------------------- what-if


describe('what-if at account scope', () => {
  it('offers the four levers', async () => {
    render(<PlanView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);

    for (const label of ['Hire', 'Lose', 'Hours', 'Wages']) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
    }
  });

  it('runs against the scoped client, state and YEAR', async () => {
    // A projection under the wrong year's statute is a wrong number that
    // somebody will act on.
    render(<PlanView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);

    await userEvent.click(screen.getByRole('button', { name: 'Project' }));

    await waitFor(() => expect(api.simulateOneZero).toHaveBeenCalledWith(
      expect.objectContaining({ client_id: 2003, state: 'GA', tax_year: 2023 }),
    ));
  });

  it('shows today against projected, with the change', async () => {
    render(<PlanView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);
    await userEvent.click(screen.getByRole('button', { name: 'Project' }));

    expect(await screen.findByText('Projection')).toBeInTheDocument();
    expect(screen.getByText('73')).toBeInTheDocument();
    expect(screen.getByText('78')).toBeInTheDocument();
    // The answer leads, and the table carries the same figure.
    expect(screen.getByText('Credit gained · TY2023')).toBeInTheDocument();
    expect(screen.getAllByText('+$17,500')).toHaveLength(2);
  });

  it('names the statute the projection ran under', async () => {
    // "It is not a filing, but it is not a guess either."
    render(<PlanView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);
    await userEvent.click(screen.getByRole('button', { name: 'Project' }));

    expect(await screen.findByText(/TY2023.s\s*statute, not this year/)).toBeInTheDocument();
    expect(screen.getByText(/35 hours and \$636 per week/)).toBeInTheDocument();
  });

  it('surfaces a refused projection instead of showing nothing', async () => {
    // The backend refuses a year with no authored statute; the reason has to
    // reach the person who asked.
    api.simulateOneZero.mockRejectedValue(
      new Error('simulate 422 · No rule pack for GA tax year 2026.'),
    );
    render(<PlanView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);

    await userEvent.click(screen.getByRole('button', { name: 'Project' }));
    expect(await screen.findByText(/No rule pack for GA tax year 2026/)).toBeInTheDocument();
  });

  it('asks for a single program rather than guessing a jurisdiction', () => {
    render(<PlanView scope={scope({ programCode: 'all' })} scopeOptions={SCOPE_OPTIONS} />);

    expect(screen.getByText(/Select a single program/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Project' })).not.toBeInTheDocument();
  });

  it('switching lever clears the previous projection', async () => {
    // A result labelled "Hire" sitting under a "Wages" selection is the stale
    // -value-under-a-new-heading bug in a different costume.
    render(<PlanView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);
    await userEvent.click(screen.getByRole('button', { name: 'Project' }));
    await screen.findByText('Projection');

    await userEvent.click(screen.getByRole('button', { name: 'Wages' }));
    expect(screen.queryByText('Projection')).not.toBeInTheDocument();
  });
});

// --------------------------------------------------------- one location

const UNIT_RESULT = {
  scope: { client_id: 2003, worksite_id: 'GA_GA-016', state: 'GA', tax_year: 2023, method: 'min_max' },
  detail: 'Added 2 full-time heads at GA_GA-016',
  base_year: 2020,
  series_years: [2020, 2023],
  eligibility_floors: { min_weekly_hours: 35, min_weekly_wages: 636 },
  method_note: 'Priced as the location grid prices it.',
  baseline: { average_headcount: 7.67, net_new_vs_base: 0.34, threshold: 2, jobs_margin: -1.66, status: 'below_minimum', annual_credit_usd: 0, series_credit_usd: 0 },
  projected: { average_headcount: 9.67, net_new_vs_base: 2.34, threshold: 2, jobs_margin: 0.34, status: 'above_minimum', annual_credit_usd: 8190, series_credit_usd: 8190 },
  delta: { average_headcount: 2, net_new_vs_base: 2, annual_credit_usd: 8190, series_credit_usd: 8190 },
};

describe('what-if at one location', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchClientUnits').mockResolvedValue({
      items: [{ worksite_id: 'GA_GA-016' }, { worksite_id: 'GA_GA-004' }],
      units: [{ worksite_id: 'GA_GA-016', name: 'Valdosta Site 16' }],
    });
    vi.spyOn(api, 'simulateUnit').mockResolvedValue(UNIT_RESULT);
  });

  const levers = (whatIf, onChangeUnit = vi.fn()) => render(
    <PlanLevers
      scope={{ ...scope(), jurisdiction: 'GA' }}
      clientName="Ironbridge Logistics"
      whatIf={{ method: 'min_max', year: null, action: null, magnitude: null, autorun: false, ...whatIf }}
      onChangeUnit={onChangeUnit}
    />,
  );

  it('offers the client\u2019s locations in the header, and says when one is set', async () => {
    const onChangeUnit = vi.fn();
    levers({ unitId: null }, onChangeUnit);
    const select = await screen.findByRole('combobox', { name: /Filter the what-if to one location/ });
    await waitFor(() => expect(screen.getByRole('option', { name: 'Valdosta Site 16 · GA_GA-016' })).toBeInTheDocument());
    await userEvent.selectOptions(select, 'GA_GA-016');
    expect(onChangeUnit).toHaveBeenCalledWith('GA_GA-016');
  });

  it('a pre-filled link runs once, against the location, not the client', async () => {
    levers({ unitId: 'GA_GA-016', action: 'add_headcount', magnitude: 2, autorun: true });
    await waitFor(() => expect(api.simulateUnit).toHaveBeenCalledTimes(1));
    expect(api.simulateUnit).toHaveBeenCalledWith(expect.objectContaining({
      clientId: 2003, worksiteId: 'GA_GA-016', taxYear: 2023, action: 'add_headcount', magnitude: 2,
    }));
    expect(api.simulateOneZero).not.toHaveBeenCalled();
    expect(screen.getByRole('spinbutton', { name: 'Hire amount' })).toHaveValue(2);
  });

  it('shows the grid\u2019s own reading moving, against its own base year', async () => {
    levers({ unitId: 'GA_GA-016', action: 'add_headcount', magnitude: 2, autorun: true });
    expect(await screen.findByText('Projection · GA_GA-016')).toBeInTheDocument();
    expect(screen.getByText('Net new vs TY2020 base')).toBeInTheDocument();
    expect(screen.getByText('1.66 short')).toBeInTheDocument();
    expect(screen.getByText('0.34 over')).toBeInTheDocument();
    expect(screen.getByText('Below minimum')).toBeInTheDocument();
    expect(screen.getByText('Above minimum')).toBeInTheDocument();
    expect(screen.getAllByText('+$8,190').length).toBeGreaterThan(0);
  });

  it('a pasted link still runs when the jurisdiction resolves after the page', async () => {
    const props = {
      clientName: 'Ironbridge Logistics',
      whatIf: { method: 'min_max', year: null, unitId: 'GA_GA-016', action: 'add_headcount', magnitude: 2, autorun: true },
      onChangeUnit: vi.fn(),
    };
    const { rerender } = render(<PlanLevers scope={{ ...scope(), jurisdiction: null }} {...props} />);
    expect(api.simulateUnit).not.toHaveBeenCalled();
    rerender(<PlanLevers scope={{ ...scope(), jurisdiction: 'GA' }} {...props} />);
    await waitFor(() => expect(api.simulateUnit).toHaveBeenCalledTimes(1));
  });

  const OPEN_RESULT = {
    ...UNIT_RESULT,
    scope: { ...UNIT_RESULT.scope, tax_year: 2026 },
    baseline: { ...UNIT_RESULT.baseline, status: 'in_progress', qualified: false },
    projected: { ...UNIT_RESULT.projected, status: 'in_progress', qualified: true, annual_credit_usd: 0 },
    delta: { ...UNIT_RESULT.delta, annual_credit_usd: 0 },
    open_year: { months_closed: 7, note: 'TY2026 is still open. Both sides are read on its 7 closed months.' },
  };

  it('an OPEN year reads on track and prices the gain as a labelled run-rate (TY2026)', async () => {
    api.simulateUnit.mockResolvedValue({
      ...OPEN_RESULT,
      run_rate: { basis: 'run_rate', before_usd: 14000, after_usd: 31500, delta_usd: 17500, note: 'Run-rate estimate.' },
    });
    levers({ unitId: 'GA_GA-016', year: 2026, action: 'add_headcount', magnitude: 2, autorun: true });
    expect(await screen.findByText(/read on its 7 closed months/)).toBeInTheDocument();
    expect(screen.getByText('Behind pace')).toBeInTheDocument();
    expect(screen.getByText('On track')).toBeInTheDocument();
    // Never presented as a calculation: the label and the row both say run-rate.
    expect(screen.getByText('Credit gained · TY2026 run-rate')).toBeInTheDocument();
    expect(screen.getByText(/Estimate if TY2026 closes at this pace/)).toBeInTheDocument();
    expect(screen.getByText('$14,000 → $31,500')).toBeInTheDocument();
    expect(screen.getByText(/Annual credit, TY2026 · run-rate est\./)).toBeInTheDocument();
    expect(screen.getAllByText('+$17,500').length).toBeGreaterThan(0);
  });

  it('an OPEN year with no run-rate prices nothing rather than $0', async () => {
    api.simulateUnit.mockResolvedValue(OPEN_RESULT);
    levers({ unitId: 'GA_GA-016', year: 2026, action: 'add_headcount', magnitude: 2, autorun: true });
    expect(await screen.findByText(/read on its 7 closed months/)).toBeInTheDocument();
    expect(screen.getAllByText(/Not priced until TY\d+ closes/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/run-rate est\./)).not.toBeInTheDocument();
  });

  it('editing the magnitude by hand does not snap it back to the link', async () => {
    levers({ unitId: 'GA_GA-016', action: 'add_headcount', magnitude: 2, autorun: false });
    const input = await screen.findByRole('spinbutton', { name: 'Hire amount' });
    await userEvent.clear(input);
    await userEvent.type(input, '3');
    expect(input).toHaveValue(3);
  });

  it('clearing the filter goes back to the whole client', async () => {
    const onChangeUnit = vi.fn();
    levers({ unitId: 'GA_GA-016' }, onChangeUnit);
    await userEvent.click(screen.getByRole('button', { name: 'Clear the GA_GA-016 filter' }));
    expect(onChangeUnit).toHaveBeenCalledWith(null);
  });
});


// --------------------------------------------------------- one employee

describe('what-if for a stack of employees (WI-19, 28 Sep)', () => {
  const employee = (over) => ({
    record_token: 'tok0', employee_id: '200300054', worksite_id: 'GA_GA-002', worksites: ['GA_GA-002'],
    designation: 'T1', tier: 1, tier_source: 'prototype',
    additional_weekly_hours: 2.38, hourly_raise: 0,
    applied: { pace_weekly_hours: 34.19, projected_weekly_hours: 36.57, rate: 24.1, projected_rate: 24.1, periods_changed: 9 },
    before: { eligible: false, avg_weekly_hours: 33.92, avg_weekly_wages: 817.47 },
    after: { eligible: true, avg_weekly_hours: 35.02, avg_weekly_wages: 844.0 },
    ...over,
  });
  const RESULT = {
    scope: { client_id: 2003, state: 'GA', tax_year: 2023, method: 'min_max', as_of: '2023-08-31' },
    employees: [
      employee(),
      employee({
        record_token: 'tok1', employee_id: '200300077', additional_weekly_hours: 0.5, hourly_raise: 3.25,
        applied: { pace_weekly_hours: 40, projected_weekly_hours: 40.5, rate: 15, projected_rate: 18.25, periods_changed: 9 },
      }),
    ],
    locations: [{
      worksite_id: 'GA_GA-002', base_year: 2020, threshold: 2, designation: 'T1', tier: 1, tier_source: 'prototype',
      before: { average_headcount: 22.0, net_new_vs_base: 1.2, jobs_margin: -0.8, qualified: false, annual_credit_usd: 0 },
      after: { average_headcount: 24.0, net_new_vs_base: 3.2, jobs_margin: 1.2, qualified: true, annual_credit_usd: 11200 },
    }],
    summary: { employees: 2, became_eligible: 2, lost_eligibility: 0, locations_moved: 1 },
    client: { annual_credit_usd_before: 0, annual_credit_usd_after: 11200, annual_credit_usd_delta: 11200 },
    eligibility_floors: { min_weekly_hours: 35, min_weekly_wages: 636 },
    method_note: 'All 2 changes are applied together.',
  };
  const STACK = [{ token: 'tok0', hours: 2.38, raise: 0 }, { token: 'tok1', hours: 0.5, raise: 3.25 }];
  const CONTEXT = {
    tok0: { record_token: 'tok0', employee_id: '200300054', worksite_id: 'GA_GA-002', designation: 'T1', tier: 1, tier_source: 'prototype', avg_weekly_hours: 33.92, avg_weekly_wages: 817.47, implied_hourly_rate: 24.1 },
  };

  beforeEach(() => { vi.spyOn(api, 'simulateEmployees').mockResolvedValue(RESULT); });

  const stack = (whatIf, onChangeStack = vi.fn(), context = CONTEXT) => render(
    <PlanLevers
      scope={{ ...scope(), jurisdiction: 'GA' }}
      clientName="Ironbridge Logistics"
      whatIf={{ unitId: null, method: 'min_max', year: 2023, stack: STACK, autorun: false, ...whatIf }}
      stackContext={context}
      onChangeStack={onChangeStack}
    />,
  );

  it('lists every stacked employee with where they work and what they earn', () => {
    stack({});
    expect(screen.getByText(/these 2 employees work differently/)).toBeInTheDocument();
    expect(screen.getByText('200300054')).toBeInTheDocument();
    expect(screen.getByText('GA_GA-002')).toBeInTheDocument();
    expect(screen.getByText('T1')).toBeInTheDocument();
    expect(screen.getByText('33.92')).toBeInTheDocument();
    expect(screen.getByText('$24.10')).toBeInTheDocument();
    // Someone added from a link we did not see is named by record, never guessed.
    expect(screen.getByText(/record tok1/)).toBeInTheDocument();
    expect(screen.getByRole('spinbutton', { name: 'More hours a week for 200300054' })).toHaveValue(2.38);
    expect(screen.getByRole('spinbutton', { name: /Raise in dollars an hour for record tok1/ })).toHaveValue(3.25);
  });

  it('runs once on arrival, every change together, by record token', async () => {
    stack({ autorun: true });
    await waitFor(() => expect(api.simulateEmployees).toHaveBeenCalledTimes(1));
    expect(api.simulateEmployees).toHaveBeenCalledWith(expect.objectContaining({
      clientId: 2003, taxYear: 2023,
      employees: [
        { recordToken: 'tok0', additionalWeeklyHours: 2.38, hourlyRaise: 0 },
        { recordToken: 'tok1', additionalWeeklyHours: 0.5, hourlyRaise: 3.25 },
      ],
    }));
    expect(api.simulateOneZero).not.toHaveBeenCalled();
  });

  it('projects what was typed, not what the link said', async () => {
    stack({});
    const hours = screen.getByRole('spinbutton', { name: 'More hours a week for 200300054' });
    await userEvent.clear(hours);
    await userEvent.type(hours, '4');
    await userEvent.click(screen.getByRole('button', { name: 'Project all 2' }));
    await waitFor(() => expect(api.simulateEmployees).toHaveBeenCalledTimes(1));
    expect(api.simulateEmployees.mock.calls[0][0].employees[0]).toEqual({ recordToken: 'tok0', additionalWeeklyHours: '4', hourlyRaise: 0 });
  });

  it('answers in one line, then per person and per location', async () => {
    stack({ autorun: true });
    expect(await screen.findByText(/2 of 2 become eligible · 1 location changes reading/)).toBeInTheDocument();
    expect(screen.getByText('Credit gained · TY2023')).toBeInTheDocument();
    expect(screen.getByText('$0 → $11,200')).toBeInTheDocument();
    expect(screen.getByText('34.19 → 36.57 hrs/wk')).toBeInTheDocument();
    expect(screen.getByText('40.00 → 40.50 hrs/wk · $15.00 → $18.25/hr')).toBeInTheDocument();
    expect(screen.getAllByText('Not eligible')).toHaveLength(2);
    expect(screen.getAllByText('Eligible')).toHaveLength(2);
    expect(screen.getByText('Client annual credit, TY2023')).toBeInTheDocument();
  });

  it('an open year leads with the run-rate gain, and states no client total', async () => {
    api.simulateEmployees.mockResolvedValue({
      ...RESULT,
      scope: { ...RESULT.scope, tax_year: 2026 },
      locations: [{
        ...RESULT.locations[0], in_progress: true,
        run_rate: { before_usd: 0, after_usd: 7000, delta_usd: 7000 },
      }],
      client: { ...RESULT.client, run_rate: { basis: 'run_rate', delta_usd: 7000, before_usd: 0, after_usd: 7000, locations: 1, note: 'Run-rate estimate.' } },
    });
    stack({ autorun: true, year: 2026 });
    expect(await screen.findByText('Credit gained · TY2026 run-rate')).toBeInTheDocument();
    expect(screen.getByText(/GA_GA-002 · annual credit, run-rate est\./)).toBeInTheDocument();
    // Before → after is over the locations the stack touches, and says so.
    expect(screen.getByText(/Across the 1 location the stack touches/)).toBeInTheDocument();
    expect(screen.queryByText(/Client annual credit/)).not.toBeInTheDocument();
  });

  it('removing one keeps the others and their edits; clearing goes back to the levers', async () => {
    const onChangeStack = vi.fn();
    stack({}, onChangeStack);
    const raise = screen.getByRole('spinbutton', { name: /Raise in dollars an hour for record tok1/ });
    await userEvent.clear(raise);
    await userEvent.type(raise, '5');
    await userEvent.click(screen.getByRole('button', { name: 'Remove 200300054 from the stack' }));
    expect(onChangeStack).toHaveBeenLastCalledWith([{ token: 'tok1', hours: 0.5, raise: '5' }]);
    await userEvent.click(screen.getByRole('button', { name: 'Clear the stack' }));
    expect(onChangeStack).toHaveBeenLastCalledWith([]);
  });
});

// --------------------------------------------------------- WI-22: the hired role

describe('Hire says what the role is (WI-22)', () => {
  it('sends hours and pay when given, client-wide', async () => {
    render(<PlanView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);
    await userEvent.type(screen.getByRole('spinbutton', { name: 'Hours a week for each hire' }), '30');
    await userEvent.type(screen.getByRole('spinbutton', { name: 'Hourly pay for each hire' }), '18');
    await userEvent.click(screen.getByRole('button', { name: 'Project' }));
    await waitFor(() => expect(api.simulateOneZero).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'add_headcount', hire_weekly_hours: 30, hire_hourly_rate: 18 }),
    ));
  });

  it('leaves both out when blank, so Hire means what it always meant', async () => {
    render(<PlanView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);
    await userEvent.click(screen.getByRole('button', { name: 'Project' }));
    await waitFor(() => expect(api.simulateOneZero).toHaveBeenCalled());
    const payload = api.simulateOneZero.mock.calls[0][0];
    expect(payload).not.toHaveProperty('hire_weekly_hours');
    expect(payload).not.toHaveProperty('hire_hourly_rate');
  });

  it('offers the role only on Hire', async () => {
    render(<PlanView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);
    await userEvent.click(screen.getByRole('button', { name: 'Hours' }));
    expect(screen.queryByRole('spinbutton', { name: 'Hours a week for each hire' })).not.toBeInTheDocument();
  });

  it('sends the role to a location what-if too', async () => {
    vi.spyOn(api, 'fetchClientUnits').mockResolvedValue({ items: [{ worksite_id: 'GA_GA-016' }], units: [] });
    vi.spyOn(api, 'simulateUnit').mockResolvedValue(UNIT_RESULT);
    render(
      <PlanLevers
        scope={{ ...scope(), jurisdiction: 'GA' }}
        clientName="Ironbridge Logistics"
        whatIf={{ unitId: 'GA_GA-016', method: 'min_max', year: null, action: null, magnitude: null, autorun: false }}
        onChangeUnit={vi.fn()}
      />,
    );
    await userEvent.type(screen.getByRole('spinbutton', { name: 'Hours a week for each hire' }), '40');
    await userEvent.click(screen.getByRole('button', { name: 'Project' }));
    await waitFor(() => expect(api.simulateUnit).toHaveBeenCalledWith(
      expect.objectContaining({ worksiteId: 'GA_GA-016', hireWeeklyHours: 40, hireHourlyRate: null }),
    ));
  });
});
