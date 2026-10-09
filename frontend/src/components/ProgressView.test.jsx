/**
 * How am I doing: the verdict, and the cohort that used to be a second page.
 *
 * Near the line was its own nav entry rendering a hundred employees, while this
 * view rendered eight of the same list with the method locked to Min-Max. They
 * were never two cohorts — `get_in_year_progress` calls `handle_get_proximity`
 * outright, precisely so the two screens could not disagree. Two entries for one
 * answer is how somebody comes away believing there are two answers.
 *
 * These tests pin what the merge has to preserve: the verdict stays first, the
 * cohort is the FULL one with its controls, and portfolio scope keeps the half
 * that works across the book instead of losing the whole page.
 */
import { render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ProgressView from './ProgressView.jsx';
import { PORTFOLIO } from '../lib/scopeDimension.js';
import * as api from '../api.js';

const SCOPE_OPTIONS = {
  clients: [{ account_id: 2001, name: 'Cascade Restaurants', synthetic: true }],
  // Two programmes, so `programCode: 'all'` derives two jurisdictions. With one
  // programme it derives one and the guard never fires — a fixture that makes
  // the test pass for the wrong reason.
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
  clientId: 2001, programCode: 'GA_JTC', year: 2023, ...overrides,
});

const PROGRESS = {
  on_track: false,
  threshold: 2,
  projected_net_new: 1.25,
  gap_to_finish: 0.75,
  projected_annual_credit_usd: 43_750,
  as_of: '2023-09-30',
  months_elapsed: 9,
  ytd_average_headcount: 25.5,
  prior_year_average_headcount: 24.25,
  finish_line_headcount: 26.25,
  has_prior_year_payroll: true,
  base_is_meaningful: true,
  base_caveat: null,
  is_estimate: true,
  denominator_note: 'Average headcount over 9 closed month(s), not 12.',
};

const PROXIMITY = {
  floors: {
    program_code: 'GA_JTC', tax_year: 2023,
    minimum_average_weekly_hours: 35.0,
    minimum_average_weekly_wages_usd: 636.0,
    threshold_hourly_rate: 18.17,
    source: 'rules/ga_jtc/2023.json',
  },
  band_weekly_hours: 5,
  evaluated: 300, eligible: 120, ineligible: 180,
  failure_modes: { hours_only: 4, wages_only: 2, both: 174 },
  within_band: 6, rate_limited_in_band: 0, exceeds_plausible_week_in_band: 0,
  returned: 6,
  bands: [
    { within_weekly_hours: 1, employees: 1, plausible: 1 },
    { within_weekly_hours: 2, employees: 3, plausible: 3 },
    { within_weekly_hours: 5, employees: 6, plausible: 6 },
    { within_weekly_hours: 10, employees: 9, plausible: 9 },
  ],
  // Nine rows, because the point of the merge is that the page stopped
  // truncating at eight.
  cohort: Array.from({ length: 9 }, (_, index) => ({
    employee_id: `E0${index + 100}`,
    weeks_worked: 51.86, avg_weekly_hours: 34.5, avg_weekly_wages: 800,
    eligible: false, failed: ['hours'], failure_mode: 'hours_only',
    hours_gap_per_week: 0.5, wages_gap_per_week: 0,
    implied_hourly_rate: 23.19, threshold_hourly_rate: 18.17,
    rate_limited: false, additional_weekly_hours: 0.5,
    projected_weekly_hours: 35.0, exceeds_plausible_week: false,
    hourly_rate_to_qualify: null,
  })),
  method_note: 'Additional hours are priced at each employee\u2019s own implied hourly rate.',
  state: 'GA', program_code: 'GA_JTC', tax_year: 2023,
  method: 'min_max', account_id: 2001,
};

beforeEach(() => {
  vi.spyOn(api, 'fetchInYearProgress').mockResolvedValue(PROGRESS);
  vi.spyOn(api, 'fetchEmployeeProximity').mockResolvedValue(PROXIMITY);
});

afterEach(() => { vi.restoreAllMocks(); });

describe('How am I doing', () => {
  it('answers the question before showing any of the working', async () => {
    render(<ProgressView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);

    expect(await screen.findByText(/Short by 0.75 jobs/)).toBeInTheDocument();
  });

  it('carries the whole near-the-line cohort, not a truncated copy of it', async () => {
    // The old page rendered `cohort.slice(0, 8)`. Nine rows is the smallest
    // fixture that tells the two apart.
    render(<ProgressView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);

    await screen.findByText('E0100');
    expect(screen.getByText('E0108')).toBeInTheDocument();
  });

  it('keeps the band and method controls the separate page owned', async () => {
    // Losing these turns a filterable cohort back into a fixed list, which is
    // what made the two pages worth keeping apart in the first place.
    render(<ProgressView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);

    await screen.findByText('E0100');
    expect(screen.getByLabelText(/Method/)).toBeInTheDocument();
    expect(screen.getByRole('group', { name: /Within/ })).toBeInTheDocument();
  });

  it('says the cohort is measured over a different period than the verdict', async () => {
    // The verdict counts closed months; the cohort runs the certified methods
    // over the whole year. On two pages nobody had to reconcile that. On one
    // page it is visible, so it has to be stated.
    render(<ProgressView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);

    expect(
      await screen.findByText(/Measured across the whole of 2023/),
    ).toBeInTheDocument();
  });

  it('drops both halves under portfolio scope, in one statement', async () => {
    // Both halves are questions about ONE client's year. The cohort looked like
    // an exception because it answered at portfolio scope — but it was
    // answering from the configured tenant and labelling it "All accounts".
    // The embedded cohort stays silent here so the page shows one explanation
    // rather than two stacked callouts describing the same limit.
    render(
      <ProgressView scope={scope({ clientId: PORTFOLIO })} scopeOptions={SCOPE_OPTIONS} />,
    );

    expect(
      await screen.findByText(/Select one client for an on-track verdict/),
    ).toBeInTheDocument();
    expect(screen.queryByText('E0100')).not.toBeInTheDocument();
    expect(api.fetchInYearProgress).not.toHaveBeenCalled();
  });

  it('asks for one programme rather than measuring against two statutes', () => {
    render(
      <ProgressView scope={scope({ programCode: 'all' })} scopeOptions={SCOPE_OPTIONS} />,
    );

    expect(screen.getByText(/Select a single program/)).toBeInTheDocument();
  });

  it('refuses to judge progress when there is no base year to judge against', async () => {
    api.fetchInYearProgress.mockResolvedValue({
      ...PROGRESS,
      base_is_meaningful: false,
      has_prior_year_payroll: false,
      base_caveat: 'No GA payroll held for TY2022, so the base is zero.',
    });
    render(<ProgressView scope={scope()} scopeOptions={SCOPE_OPTIONS} />);

    expect(
      await screen.findByText(/Cannot judge progress/),
    ).toBeInTheDocument();
  });

  it('does not render a verdict fetched under a different client', async () => {
    const { rerender } = render(
      <ProgressView scope={scope()} scopeOptions={SCOPE_OPTIONS} />,
    );
    await screen.findByText(/Short by 0.75 jobs/);

    api.fetchInYearProgress.mockResolvedValue({ ...PROGRESS, on_track: true, projected_net_new: 9 });
    rerender(<ProgressView scope={scope({ clientId: 4242 })} scopeOptions={SCOPE_OPTIONS} />);

    await waitFor(() => {
      expect(screen.queryByText(/Short by 0.75 jobs/)).not.toBeInTheDocument();
    });
  });
});
