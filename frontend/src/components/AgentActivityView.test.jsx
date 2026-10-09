/**
 * Agent Activity: render smoke tests.
 *
 * The Workbench listed registered agents. This shows what an agent FOUND and
 * what you decided about it — and the distinction that makes it worth a screen
 * is that nothing is applied until a human chooses. An agent that silently
 * enacted its own proposal would be making the decision while appearing to ask.
 *
 * `test_findings_api.py` covers durability and the lifecycle. These cover
 * whether the screen actually puts the choice in front of somebody.
 */
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import AgentActivityView from './AgentActivityView.jsx';
import { PORTFOLIO } from '../lib/scopeDimension.js';
import * as api from '../api.js';

const SCOPE_OPTIONS = {
  clients: [{ account_id: 1001, name: 'Candle Bottle', synthetic: false }],
  programs: [{
    program_code: 'GA_JTC',
    name: 'Georgia Jobs Tax Credit',
    jurisdiction: { level: 'state', code: 'GA', name: 'Georgia' },
    authored_years: [2024, 2025],
    calculable: true,
  }],
};

const scope = (overrides = {}) => ({
  clientId: 1001, programCode: 'GA_JTC', year: 2025, windowMode: false, ...overrides,
});

const finding = (overrides = {}) => ({
  finding_id: 't2:E00200:2025-02',
  kind: 'test_of_twos',
  grain: 'instance',
  title: 'Employee counted at two worksites in one month',
  why_it_matters: 'The engine counts headcount per unit, so a person appearing at two worksites in the same month is counted twice.',
  proposes: 'assign',
  proposed_effect: 'Keeps the employee at one worksite for that month; drops the other rows.',
  employee_id: 'E00200',
  population: null,
  evidence: {
    type: 'test_of_twos', employee_id: 'E00200', month: '2025-02',
    units: [
      { worksite_id: 'GA_MAC_OPS', wages: 3121.86, hours: 120.0, periods: 3 },
      { worksite_id: 'GA_SAV_DC', wages: 1040.62, hours: 40.0, periods: 1 },
    ],
  },
  resolution: null,
  requires_decision: true,
  ...overrides,
});

const payload = (findings, summaryOverrides = {}) => ({
  client_id: 1001,
  tax_year: 2025,
  state: 'GA',
  findings,
  summary: {
    total: findings.length,
    requires_decision: findings.filter((f) => f.requires_decision).length,
    all_decided: findings.length > 0 && findings.every((f) => !f.requires_decision),
    none_found: findings.length === 0,
    by_kind: { test_of_twos: findings.length },
    ...summaryOverrides,
  },
});

beforeEach(() => {
  vi.spyOn(api, 'fetchFindings').mockResolvedValue(payload([finding()]));
  vi.spyOn(api, 'resolveFinding').mockResolvedValue({});
  vi.spyOn(api, 'reopenFinding').mockResolvedValue({});
  vi.spyOn(api, 'fetchMe').mockResolvedValue({ auth_mode: 'none', authenticated: false, upn: null });
});

afterEach(() => vi.restoreAllMocks());

// ------------------------------------------------------ the finding itself


describe('a finding explains itself', () => {
  it('says what it is, who it affects, and why it matters', async () => {
    render(<AgentActivityView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);

    expect(await screen.findByText(/counted at two worksites/)).toBeInTheDocument();
    expect(screen.getByText('E00200')).toBeInTheDocument();
    expect(screen.getByText(/counted twice/)).toBeInTheDocument();
  });

  it('shows the evidence a reviewer needs to choose between units', async () => {
    render(<AgentActivityView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);

    await screen.findByText(/counted at two worksites/);
    expect(screen.getByText('GA_MAC_OPS')).toBeInTheDocument();
    expect(screen.getByText('GA_SAV_DC')).toBeInTheDocument();
    expect(screen.getByText('120h')).toBeInTheDocument();
  });

  it('states that nothing is applied until a decision is made', async () => {
    // The property that distinguishes asking from acting.
    render(<AgentActivityView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);

    expect(await screen.findByText(/Nothing is applied until you decide/)).toBeInTheDocument();
  });
});

// ------------------------------------------------------------ the grain


describe('findings arrive at the grain a human decides at', () => {
  const policyFinding = {
    finding_id: 'policy:meaningful_pay_period:GA:2025',
    kind: 'meaningful_pay_period',
    grain: 'policy',
    title: 'Pay periods too small to be real periods',
    why_it_matters: 'Whether such periods count is one policy question, not one question per period.',
    proposes: 'drop',
    proposed_effect: 'Excludes every period below the threshold from the denominator.',
    employee_id: null,
    population: {
      instances: 32219,
      employees_affected: 5918,
      total_wages: 596447.45,
      total_hours: 23022.21,
      sample: [
        { employee_id: '16752077', worksite_id: 'GA_1134650', pay_date: '2024-02-22', wages: 12.5, hours: 1.0 },
      ],
      sample_of: 32219,
    },
    evidence: { type: 'meaningful_pay_period', units: [] },
    resolution: null,
    requires_decision: true,
  };

  it('shows one decision covering a large population', async () => {
    // On the real reference client the detectors emit 36,016 anomalies. Thirty-six
    // thousand buttons is a data dump with a UI on it.
    api.fetchFindings.mockResolvedValue({
      ...payload([policyFinding]),
      summary: {
        total: 1, requires_decision: 1, instances: 32219,
        all_decided: false, none_found: false, by_kind: { meaningful_pay_period: 32219 },
      },
    });

    render(<AgentActivityView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);

    expect(await screen.findByText(/Pay periods too small/)).toBeInTheDocument();
    expect(screen.getByText('32,219')).toBeInTheDocument();
    expect(screen.getByText('one decision covers all')).toBeInTheDocument();
  });

  it('never understates the population behind one decision', async () => {
    // "1 finding" must not read as "1 row" — the KPI says what it covers.
    api.fetchFindings.mockResolvedValue({
      ...payload([policyFinding]),
      summary: {
        total: 1, requires_decision: 1, instances: 32219,
        all_decided: false, none_found: false, by_kind: {},
      },
    });

    render(<AgentActivityView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);

    const card = (await screen.findByText('Decisions')).closest('.kpi-card');
    expect(card).toHaveTextContent('1');
    expect(card).toHaveTextContent('covering 32,219 instances');
  });

  it('offers a sample rather than the list', async () => {
    api.fetchFindings.mockResolvedValue({
      ...payload([policyFinding]),
      summary: { total: 1, requires_decision: 1, instances: 32219, all_decided: false, none_found: false, by_kind: {} },
    });

    render(<AgentActivityView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);

    expect(await screen.findByText(/1 example of 32,219/)).toBeInTheDocument();
    expect(screen.getByText(/A sample, not the list/)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------- the decision


describe('the decision reaches a human', () => {
  it('offers the proposal AND the alternatives', async () => {
    // If the only button were "Assign", the proposal would be an instruction.
    render(<AgentActivityView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);

    await screen.findByText(/counted at two worksites/);
    expect(screen.getByRole('button', { name: 'Assign' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Leave as is' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Ask client/ })).toBeInTheDocument();
  });

  it('sends the chosen worksite, not just the resolution', async () => {
    render(<AgentActivityView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);
    await screen.findByText(/counted at two worksites/);

    await userEvent.selectOptions(screen.getByRole('combobox'), 'GA_SAV_DC');
    await userEvent.click(screen.getByRole('button', { name: 'Assign' }));

    await waitFor(() => expect(api.resolveFinding).toHaveBeenCalledWith(
      't2:E00200:2025-02',
      expect.objectContaining({
        client_id: 1001, tax_year: 2025,
        resolution: 'assign', keep_worksite: 'GA_SAV_DC',
      }),
    ));
  });

  it('attributes the decision to the signed-in identity from /api/me', async () => {
    api.fetchMe.mockResolvedValue({ auth_mode: 'entra', authenticated: true, upn: 'analyst@example.com' });
    render(<AgentActivityView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);
    await screen.findByText(/counted at two worksites/);
    await waitFor(() => expect(api.fetchMe).toHaveBeenCalled());

    await userEvent.click(screen.getByRole('button', { name: 'Leave as is' }));

    await waitFor(() => expect(api.resolveFinding).toHaveBeenCalledWith(
      't2:E00200:2025-02', expect.objectContaining({ decided_by: 'analyst@example.com' }),
    ));
  });

  it('never invents a decider when nobody is signed in', async () => {
    render(<AgentActivityView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);
    await screen.findByText(/counted at two worksites/);

    await userEvent.click(screen.getByRole('button', { name: 'Leave as is' }));

    await waitFor(() => expect(api.resolveFinding).toHaveBeenCalled());
    const [, body] = api.resolveFinding.mock.calls[0];
    expect(body).not.toHaveProperty('decided_by');
  });

  it('records "leave as is" as a decision rather than doing nothing', async () => {
    // Declining to act IS an answer, and it has to be recorded — otherwise the
    // finding reappears forever and the reviewer looks ignored.
    render(<AgentActivityView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);
    await screen.findByText(/counted at two worksites/);

    await userEvent.click(screen.getByRole('button', { name: 'Leave as is' }));

    await waitFor(() => expect(api.resolveFinding).toHaveBeenCalledWith(
      't2:E00200:2025-02', expect.objectContaining({ resolution: 'accept' }),
    ));
  });

  it('shows a decided finding with who decided it', async () => {
    api.fetchFindings.mockResolvedValue(payload([finding({
      requires_decision: false,
      resolution: {
        resolution: 'assign', detail: { keep_worksite: 'GA_MAC_OPS' },
        decided_by: 'lead@example.com', decided_at: '2026-08-27T09:00:00Z',
      },
    })]));

    render(<AgentActivityView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);

    expect(await screen.findByText('assign')).toBeInTheDocument();
    expect(screen.getByText('kept at GA_MAC_OPS')).toBeInTheDocument();
    expect(screen.getByText('lead@example.com')).toBeInTheDocument();
  });

  it('can reopen a decision', async () => {
    api.fetchFindings.mockResolvedValue(payload([finding({
      requires_decision: false,
      resolution: { resolution: 'accept', decided_by: 'lead@example.com' },
    })]));

    render(<AgentActivityView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);
    await userEvent.click(await screen.findByRole('button', { name: /Reopen/ }));

    await waitFor(() => expect(api.reopenFinding).toHaveBeenCalled());
  });

  it('re-reads after a decision so the queue reflects it', async () => {
    render(<AgentActivityView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);
    await screen.findByText(/counted at two worksites/);
    api.fetchFindings.mockClear();

    await userEvent.click(screen.getByRole('button', { name: 'Leave as is' }));
    await waitFor(() => expect(api.fetchFindings).toHaveBeenCalled());
  });

  it('surfaces a rejected decision instead of appearing to succeed', async () => {
    api.resolveFinding.mockRejectedValue(
      new Error('findings 422 · assign needs keep_worksite'),
    );
    render(<AgentActivityView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);
    await screen.findByText(/counted at two worksites/);

    await userEvent.click(screen.getByRole('button', { name: 'Assign' }));
    expect(await screen.findByText(/assign needs keep_worksite/)).toBeInTheDocument();
  });
});

// ----------------------------------------------------------- the summary


describe('open findings are distinguished from answered ones', () => {
  it('counts what is awaiting a decision', async () => {
    render(<AgentActivityView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);

    const card = await screen.findByText('Awaiting a decision');
    expect(card.closest('.kpi-card')).toHaveTextContent('1');
    expect(screen.getByText(/unanswered findings affect the figures/)).toBeInTheDocument();
  });

  it('says "nothing found" differently from "all answered"', async () => {
    // A queue worked through is not the same state as a queue that was empty,
    // and conflating them hides whether anyone looked.
    api.fetchFindings.mockResolvedValue(payload([], { none_found: true, by_kind: {} }));
    const { unmount } = render(<AgentActivityView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);
    expect(await screen.findByText('Nothing found')).toBeInTheDocument();
    expect(screen.getByText(/the agent looked and found nothing/)).toBeInTheDocument();
    unmount();

    api.fetchFindings.mockResolvedValue(payload([finding({
      requires_decision: false,
      resolution: { resolution: 'accept', decided_by: 'lead@example.com' },
    })]));
    render(<AgentActivityView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);
    expect(await screen.findByText('All answered')).toBeInTheDocument();
  });
});

// ------------------------------------------------------------ the scope


describe('findings are per client-year', () => {
  it('asks for the scoped client, year and jurisdiction', async () => {
    render(<AgentActivityView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);
    await waitFor(() => expect(api.fetchFindings).toHaveBeenCalledWith(1001, 2025, 'GA'));
  });

  it('asks for a client rather than guessing at portfolio scope', async () => {
    render(
      <AgentActivityView scope={scope({ clientId: PORTFOLIO })} scopeOptions={SCOPE_OPTIONS} />,
    );

    expect(await screen.findByText(/Select a client to review theirs/)).toBeInTheDocument();
    expect(api.fetchFindings).not.toHaveBeenCalled();
  });

  it('surfaces a failed read rather than an empty queue', async () => {
    api.fetchFindings.mockRejectedValue(new Error('findings 503 · store unavailable'));
    render(<AgentActivityView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);

    expect(await screen.findByText(/store unavailable/)).toBeInTheDocument();
  });
});
