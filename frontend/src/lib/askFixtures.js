/**
 * Fixtures for the Ask workspace's evidence pane: invented, customer-neutral,
 * and shaped like the platform's tool-result envelope
 * (docs/design/ASK-EVIDENCE-CONTRACT.md). They exist so the pane is developed
 * and tested without a backend that emits `evidence` events, and they are what
 * `?askFixture=1` replays in a dev build. Nothing here is a certified figure.
 *
 * Every figure is a STRING, because the pane renders the platform's text
 * verbatim; a test asserts that every figure in the DOM equals one of these.
 */

export const ELIGIBILITY_EVIDENCE = {
  id: 'ev-eligibility-1',
  tool: 'eligibility',
  title: 'Eligibility',
  facts: { client: 'Example Client A', tax_year: 'TY2023', method: 'Min-Max' },
  blocks: [
    {
      kind: 'kpis',
      title: 'Headline',
      rows: [
        { label: 'Eligible employees', value: '539', sub: 'of 10,236 evaluated', tone: 'above-min' },
        { label: 'Annual average headcount', value: '410.13', sub: 'Min-Max, fiscal window' },
        { label: 'Within 5 hrs of the floor', value: '24', tone: 'partial' },
      ],
    },
    {
      kind: 'table',
      title: 'Locations',
      columns: ['Location', 'Net new', 'Reading'],
      align: ['left', 'right', 'left'],
      rows: [
        ['GA_GA-001', '-4.0', 'Below minimum'],
        ['GA_GA-010', '3.0', 'No payroll'],
        ['GA_GA-016', '0.34', 'Below minimum'],
      ],
    },
    {
      kind: 'callout',
      title: 'Why this reading',
      tone: 'partial',
      text: 'Three of ten locations are below the statutory minimum for the year, measured against each location\u2019s own base year.',
    },
  ],
  provenance: {
    run_id: 'run-0123456789ab',
    rule_pack: 'ga_jtc/2023',
    trail_hash: 'b1946ac92492d2347c6235b4d2611184f1a3e9d0c5b5f5f6a1c9a8d2a1c0ffee',
  },
  disclaimer: 'Computed by the calculation engine from payroll. Not tax advice.',
};

export const TREND_EVIDENCE = {
  id: 'ev-trend-1',
  tool: 'trend',
  title: 'Trend',
  blocks: [
    {
      kind: 'table',
      title: 'Headcount by year',
      columns: ['Tax year', 'Average headcount', 'Credit'],
      align: ['left', 'right', 'right'],
      rows: [
        ['TY2021', '25.9', '$0'],
        ['TY2022', '24.1', '$0'],
        ['TY2023', '22.4', '$0'],
      ],
    },
    { kind: 'list', title: 'Notes', rows: ['TY2021 is the base year.', 'TY2024 is declined: payroll barely touches it.'] },
  ],
  provenance: { run_id: 'run-0123456789ab', rule_pack: 'ga_jtc/2023' },
  disclaimer: 'Computed by the calculation engine from payroll. Not tax advice.',
};

export const CONFIRMATION_EVIDENCE = {
  id: 'ev-confirm-1',
  tool: 'record_decision',
  kind: 'confirmation',
  title: 'Confirm a decision',
  confirmation: {
    token: 'confirm-token-1',
    summary: 'Count E00200 at GA_MAC_OPS for 2025-02.',
    blocks: [
      {
        kind: 'table',
        title: 'What would be recorded',
        columns: ['Employee', 'Month', 'Kept at'],
        rows: [['E00200', '2025-02', 'GA_MAC_OPS']],
      },
    ],
    expires_at: '2099-01-01T00:00:00Z',
    confirm_label: 'Confirm',
    cancel_label: 'Cancel',
  },
};

export const PLAN_EVENT = {
  intents: ['eligibility', 'trend'],
  needs_client: [],
  capabilities: { eligibility: 'the credit figure', trend: 'how a client has moved' },
};

/**
 * A scripted stream for `?askFixture=1`: the same events, in the same order,
 * as the real endpoint, plus `evidence`. Never imported by a production build.
 */
export async function fixtureStream(message, onEvent) {
  const text = String(message || '').toLowerCase();
  if (text.includes('their')) {
    onEvent({ event: 'plan', data: { intents: [], needs_client: ['trend'], capabilities: {} } });
    onEvent({ event: 'agent_start', data: { agent: 'OrchestratorAgent' } });
    onEvent({ event: 'token', data: { agent: 'OrchestratorAgent', content: 'Which client do you mean?' } });
    onEvent({
      event: 'clarify',
      data: {
        message,
        reason: 'does not say which client it means',
        choices: [
          { client_id: 2001, name: 'Example Client A', tax_year: 2023 },
          { client_id: 2002, name: 'Example Client B', tax_year: 2022 },
          { client_id: 9999, name: 'Never Run', tax_year: null },
        ],
      },
    });
    onEvent({ event: 'agent_end', data: { agent: 'OrchestratorAgent' } });
    onEvent({ event: 'done', data: {} });
    return;
  }
  onEvent({ event: 'plan', data: PLAN_EVENT });
  onEvent({ event: 'agent_start', data: { agent: 'CreditRulesAgent' } });
  for (const word of 'Three of ten locations are below the minimum. The figures are on the right.'.split(' ')) {
    onEvent({ event: 'token', data: { agent: 'CreditRulesAgent', content: `${word} ` } });
  }
  onEvent({ event: 'agent_end', data: { agent: 'CreditRulesAgent' } });
  onEvent({ event: 'evidence', data: ELIGIBILITY_EVIDENCE });
  onEvent({ event: 'evidence', data: TREND_EVIDENCE });
  if (text.includes('confirm') || text.includes('decision')) {
    onEvent({ event: 'evidence', data: CONFIRMATION_EVIDENCE });
  }
  onEvent({ event: 'done', data: {} });
}
