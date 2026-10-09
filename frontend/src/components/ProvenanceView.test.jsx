/**
 * B5: what survived the retirement of Data Ingestion, and where it landed.
 *
 * The editorial test is "show only what brings value to the process, never how
 * the sausage is made". Applying it to that view kept four panels and cut
 * three, and a rescue is easy to get wrong in a way nobody notices: a panel
 * that quietly fails to move is indistinguishable from one that was cut on
 * purpose.
 *
 * These tests assert the placement, because the placement IS the argument. A
 * cadence conflict is a period the engine refused to count — it belongs beside
 * the denominator it changed, not on a screen about ingestion. The source
 * manifest is what lets somebody re-run this, so it belongs under Defend.
 */
import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ProvenanceView from './ProvenanceView.jsx';
import { EligibilityView, OneZeroView } from './ReferenceViews.jsx';
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
  },
  source: {
    controls: {
      physical_rows: 391000, usable_rows: 384433, padded_rows: 6567,
      zero_hour_rows: 1204, negative_hour_rows: 88,
      negative_wage_rows: 91, pay_date_before_period_end_rows: 3,
    },
    files: [
      { file_name: 'One.csv', usable_rows: 100000, padded_rows: 10, sha256: 'sha256:aaa' },
      { file_name: 'Two.csv', usable_rows: 100000, padded_rows: 10, sha256: 'sha256:bbb' },
    ],
  },
  selection: { included: 384418, excluded_pay_date_after_fy: 15 },
  collapse: { collapsed_rows: 382180, duplicate_rows_collapsed: 2238 },
  boundary: {
    boundary_complete: false,
    status: 'missing_leading_lookback',
    prior_ppe_paid_in_fy_rows: 1200,
    crossing_start_rows: 47,
    current_ppe_paid_after_fy_rows: 15,
    earliest_valid_pay_period_start: '2023-07-28',
  },
  eligibility: {
    employees_with_totals: 10236,
    min_max: { employees_evaluated: 10236, eligible_employees: 539 },
    pay_period: { employees_evaluated: 10236, eligible_employees: 656 },
    reconciliation: { eligible_both: 500, min_max_only: 39, pay_period_only: 156 },
    thresholds: {
      source_tax_year: 2023, minimum_average_weekly_hours: 35,
      minimum_average_weekly_wages_usd: 636, lowest_wage_county: 'Glascock',
    },
    denominator_invariant: {
      invariant_holds: true, pay_period_gt_min_max: 0,
      pay_period_gt_min_max_over_review_tolerance: 0,
      pay_period_over_52_weeks: 0, maximum_weeks_without_review: 53,
    },
    pay_period_controls: {
      source_period_keys: 384418, employee_pps_ppe_periods: 382180,
      same_pps_ppe_records_collapsed: 2238, conflicting_frequency_periods: 7,
    },
  },
};

beforeEach(() => {
  vi.spyOn(api, 'searchWorkspaceEligibility').mockResolvedValue({ rows: [], total: 0, offset: 0, limit: 50 });
  vi.spyOn(api, 'fetchWorkspaceAssumptions').mockResolvedValue({
    statutory: {
      program_code: 'GA_JTC', tax_year: 2023,
      minimum_average_weekly_hours: 35, minimum_average_weekly_wages_usd: 636,
      lowest_wage_county: 'Glascock', dol_report_year: 2022,
      source: 'rules/ga_jtc/2023.json', prototype_verify: false,
    },
  });
});

afterEach(() => vi.restoreAllMocks());

// ------------------------------------------------------------ what moved


describe('denominator identity moved to Eligibility', () => {
  it('shows the period-identity control beside the denominators it describes', () => {
    render(<EligibilityView summary={SUMMARY} openEmployee={() => {}} />);

    expect(screen.getByText('Denominator period identity')).toBeInTheDocument();
    expect(screen.getByText('Cadence conflicts')).toBeInTheDocument();
    // A period the engine refused to count is a decision, and it belongs next
    // to the number it changed.
    expect(screen.getByText('7')).toBeInTheDocument();
    expect(screen.getByText('excluded and flagged')).toBeInTheDocument();
  });

  it('shows boundary completeness, because it constrains every denominator', () => {
    // Without a leading lookback the first period of the year is short, and a
    // short period is a smaller denominator — which raises an average and can
    // make someone look eligible who is not.
    render(<EligibilityView summary={SUMMARY} openEmployee={() => {}} />);

    expect(screen.getByText('Fiscal boundary completeness')).toBeInTheDocument();
    expect(screen.getByText(/Leading payroll lookback is missing/)).toBeInTheDocument();
    expect(screen.getByText(/2023-07-28/)).toBeInTheDocument();
  });
});

describe('provenance moved to Defend', () => {
  it('shows run identity, which the retired Overview used to own', async () => {
    // B4 removed Overview before this move happened, so run provenance was
    // briefly homeless. A figure that cannot name its run is not defensible.
    render(<ProvenanceView summary={SUMMARY} />);

    expect(screen.getByText('Run identity')).toBeInTheDocument();
    expect(screen.getByText('GDS-STEP1-2026-08-25-v8')).toBeInTheDocument();
    expect(screen.getByText('Step 1 run')).toBeInTheDocument();
  });

  it('shows the source manifest with its per-chunk hashes', () => {
    render(<ProvenanceView summary={SUMMARY} />);

    // Scoped to the panel: "Source manifest" is also a row label in Run
    // identity, and a bare query could be satisfied by the wrong one.
    expect(screen.getByRole('heading', { name: /Source manifest/ })).toBeInTheDocument();
    expect(screen.getByText('One.csv')).toBeInTheDocument();
    expect(screen.getByText('Two.csv')).toBeInTheDocument();
  });

  it('shows what the engine deliberately did NOT repair', () => {
    // Not a progress bar. Each figure is an anomaly the engine could have
    // quietly fixed and did not.
    render(<ProvenanceView summary={SUMMARY} />);

    expect(screen.getByText('What the engine left alone')).toBeInTheDocument();
    expect(screen.getByText('Negative hours')).toBeInTheDocument();
    expect(screen.getByText('88')).toBeInTheDocument();
    expect(screen.getAllByText('corrections preserved')).toHaveLength(2);
  });

  it('names the statute each figure was computed under', async () => {
    render(<ProvenanceView summary={SUMMARY} />);

    expect(await screen.findByText('rules/ga_jtc/2023.json')).toBeInTheDocument();
    expect(screen.getByText('Glascock')).toBeInTheDocument();
  });

  it('warns loudly when the resolved floor is an unverified placeholder', async () => {
    api.fetchWorkspaceAssumptions.mockResolvedValue({
      statutory: {
        program_code: 'GA_JTC', tax_year: 2026,
        minimum_average_weekly_hours: 35, minimum_average_weekly_wages_usd: 680,
        lowest_wage_county: null, dol_report_year: null,
        source: 'rules/ga_jtc/2026.json', prototype_verify: true,
      },
    });

    render(<ProvenanceView summary={SUMMARY} />);
    expect(await screen.findByText(/Unverified placeholder/)).toBeInTheDocument();
  });

  it('still renders when the assumptions endpoint fails', async () => {
    api.fetchWorkspaceAssumptions.mockRejectedValue(new Error('boom'));
    render(<ProvenanceView summary={SUMMARY} />);

    // Run identity comes from the summary, so it must survive independently.
    expect(screen.getByText('Run identity')).toBeInTheDocument();
  });
});

describe('standing caveats are a run-level fact', () => {
  it('lists them where the run is described', () => {
    // They were reachable only by opening a per-employee drill, so a caveat
    // about the whole calculation was seen by almost nobody.
    render(<ProvenanceView summary={{
      ...SUMMARY,
      exceptions: {
        step1: ['BA-06 rounding_mode is not Access-verified.'],
        onezero: ['Test-of-twos dispositions are provisional.'],
      },
    }} />);

    expect(screen.getByText('Standing caveats')).toBeInTheDocument();
    expect(screen.getByText(/rounding_mode is not Access-verified/)).toBeInTheDocument();
    expect(screen.getByText(/dispositions are provisional/)).toBeInTheDocument();
  });

  it('says so plainly when there are none', () => {
    render(<ProvenanceView summary={{ ...SUMMARY, exceptions: { step1: [], onezero: [] } }} />);
    expect(screen.getByText('No outstanding caveats on this run.')).toBeInTheDocument();
  });

  it('does not break when the run reports no exceptions block at all', () => {
    render(<ProvenanceView summary={SUMMARY} />);
    expect(screen.getByText('Standing caveats')).toBeInTheDocument();
  });
});

describe('what the editorial test cut', () => {
  it('no longer shows raw row volumetrics', () => {
    // "391,000 physical rows" describes our machinery, not the client's
    // position. It brought nothing to the process.
    render(<ProvenanceView summary={SUMMARY} />);
    expect(screen.queryByText('Physical rows')).not.toBeInTheDocument();
    expect(screen.queryByText('391,000')).not.toBeInTheDocument();
  });

  it('no longer shows the static source-to-field contract table', () => {
    render(<ProvenanceView summary={SUMMARY} />);
    expect(screen.queryByText('Source → calculation contract')).not.toBeInTheDocument();
  });

  it('points at the employee drill for per-row lineage instead of dumping it', () => {
    // The drill already carries file and row for every included and excluded
    // line, and that is the path somebody actually takes. A searchable dump of
    // 384,433 rows is a database browser.
    render(<ProvenanceView summary={SUMMARY} />);
    expect(screen.getByText(/Per-row lineage lives on the employee/)).toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/Employee, unit, FEIN/)).not.toBeInTheDocument();
  });
});

describe('portfolio scope on the per-client views', () => {
  // `PORTFOLIO` is the string 'portfolio', not an id. Passing it through as
  // account_id is a 422, and both views used to do exactly that the moment
  // somebody switched scope to All clients mid-demo.
  beforeEach(() => {
    vi.spyOn(api, 'fetchEligibility').mockResolvedValue({});
    vi.spyOn(api, 'fetchOneZeroMatrix').mockResolvedValue({});
  });
  afterEach(() => vi.restoreAllMocks());

  const portfolio = { clientId: 'portfolio', year: 2023, jurisdiction: 'GA' };

  it('asks for a client rather than requesting the portfolio sentinel', async () => {
    render(<EligibilityView scope={portfolio} openEmployee={() => {}} />);
    expect(await screen.findByText(/Select a client to see theirs/)).toBeInTheDocument();
    expect(api.fetchEligibility).not.toHaveBeenCalled();
  });

  it('does the same on the One/Zero matrix', async () => {
    render(<OneZeroView scope={portfolio} openEmployee={() => {}} />);
    expect(await screen.findByText(/Select a client to see theirs/)).toBeInTheDocument();
    expect(api.fetchOneZeroMatrix).not.toHaveBeenCalled();
  });
});
