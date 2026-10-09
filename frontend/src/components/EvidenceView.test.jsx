/**
 * The evidence pack: one dossier, not three nav entries pointing at it.
 *
 * Provenance, Calculation walk and this page all read the same two singleton
 * endpoints. The pack already carried a hashes panel repeating run identity
 * value for value, and a table repeating the walk — so a reader defending a
 * filed number had to guess which of three pages held the answer.
 *
 * These tests pin what the merge has to deliver: the sections Provenance owned
 * are present here, the duplicated hashes panel is gone, and the full working
 * stays behind a toggle so the printed pack is still the length of a printed
 * pack.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import EvidenceView from './EvidenceView.jsx';
import * as api from '../api.js';

const SUMMARY = {
  run: {
    step1_calculation_id: 'sha256:1111111111111111',
    onezero_calculation_id: 'sha256:2222222222222222',
    source_manifest_sha256: 'sha256:3333333333333333',
    step1_assumption_set_id: 'GDS-STEP1-2026-08-25-v8',
    onezero_assumption_set_id: 'GDS-ONEZERO-2026-08-24-v7',
    code_commit: 'abc1234def',
    created_at: '2026-08-26T12:00:00Z',
    source_kind: 'lakehouse',
  },
  workspace: { client_name: 'Candle Bottle' },
  source: {
    source_kind: 'lakehouse',
    controls: {
      usable_rows: 384433, distinct_employees: 10236,
      zero_hour_rows: 1204, negative_hour_rows: 88,
      negative_wage_rows: 91, pay_date_before_period_end_rows: 3,
    },
    files: [
      { file_name: 'One.csv', usable_rows: 100000, padded_rows: 10, sha256: 'sha256:aaa' },
    ],
  },
  eligibility: {
    min_max: { eligible_employees: 539 },
    pay_period: { eligible_employees: 656 },
    thresholds: { source_tax_year: 2023 },
  },
  equivalence: {
    matches: true,
    source_kind: 'lakehouse',
    expected: { employees_evaluated: 10236, min_max_eligible: 539, pay_period_eligible: 656 },
    observed: { employees_evaluated: 10236, min_max_eligible: 539, pay_period_eligible: 656 },
  },
  exceptions: { step1: [], onezero: [] },
};

const WALK = {
  run_context: { calculation_id: 'sha256:1111', code_ref: 'tools/credit_math.py' },
  steps: [
    {
      step_id: 'S-01', stage: 'selection', method: 'shared',
      formula: 'rows WHERE pay_date IN window', decision_basis: 'BA-02',
      inputs: { rows: 391000 }, parameters: { window: '2023-07-28..2024-07-31' },
      output: { rows: 384418 }, assumption_ids: ['BA-02'], exceptions: [],
      citation: 'BA-02', calculation_id: 'sha256:1111', code_ref: 'tools/x.py',
      source_hash: 'sha256:aaa', config_hash: 'sha256:bbb', timestamp: '2026-08-26T12:00:00Z',
    },
  ],
};

const STATUTORY = {
  statutory: {
    program_code: 'GA_JTC', tax_year: 2023,
    minimum_average_weekly_hours: 35, minimum_average_weekly_wages_usd: 636,
    lowest_wage_county: 'Glascock', dol_report_year: 2022,
    source: 'rules/ga_jtc/2023.json', prototype_verify: false,
  },
};

beforeEach(() => {
  vi.spyOn(api, 'fetchWorkspaceCalculationWalk').mockResolvedValue(WALK);
  vi.spyOn(api, 'fetchWorkspaceAssumptions').mockResolvedValue(STATUTORY);
});

afterEach(() => { vi.restoreAllMocks(); });

describe('the evidence pack', () => {
  it('carries the run identity that Provenance used to own', async () => {
    render(<EvidenceView summary={SUMMARY} />);

    expect(await screen.findByText('Run identity')).toBeInTheDocument();
    expect(screen.getByText('GDS-STEP1-2026-08-25-v8')).toBeInTheDocument();
  });

  it('carries the source manifest and the controls the engine did not apply', async () => {
    render(<EvidenceView summary={SUMMARY} />);

    expect(await screen.findByRole('heading', { name: /Source manifest/ })).toBeInTheDocument();
    expect(screen.getByText('What the engine left alone')).toBeInTheDocument();
    expect(screen.getByText('Negative hours')).toBeInTheDocument();
  });

  it('names the statute the figures were computed under', async () => {
    render(<EvidenceView summary={SUMMARY} />);

    expect(await screen.findByText('rules/ga_jtc/2023.json')).toBeInTheDocument();
  });

  it('does not repeat run identity as a separate hashes panel', async () => {
    // The pack used to render both. Two panels of the same six values is how a
    // reader starts wondering whether they are the same six values.
    render(<EvidenceView summary={SUMMARY} />);
    await screen.findByText('Run identity');

    expect(screen.queryByText('Hashes')).not.toBeInTheDocument();
    expect(screen.getAllByText('GDS-STEP1-2026-08-25-v8')).toHaveLength(1);
  });

  it('shows the walk as a summary and keeps the full working behind a toggle', async () => {
    // Print is the deliverable. Expanding every step's inputs and outputs by
    // default turns a cover-sheet-and-result pack into a hundred pages.
    render(<EvidenceView summary={SUMMARY} />);

    expect(await screen.findByText('rows WHERE pay_date IN window')).toBeInTheDocument();
    expect(screen.queryByText('Reproducibility envelope')).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'full working' }));

    expect(await screen.findByText('Reproducibility envelope')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'summary' })).toBeInTheDocument();
  });

  it('still renders the cover sheet when the assumptions endpoint fails', async () => {
    api.fetchWorkspaceAssumptions.mockRejectedValue(new Error('boom'));
    render(<EvidenceView summary={SUMMARY} />);

    expect(await screen.findByText('Cover sheet')).toBeInTheDocument();
    expect(screen.getByText('Candle Bottle')).toBeInTheDocument();
  });
});
