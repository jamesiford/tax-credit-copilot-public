/**
 * The Programs page carries no rule-ingestion control, on purpose.
 *
 * "Re-run ingestion" returned a captured snapshot in ~50ms without touching the
 * network, then printed "4 trusted URLs monitored for drift" about URLs nobody
 * had checked. "Check against DCA source" failed on a Web IQ 401, and had it
 * succeeded, "Confirm & apply" wrote to process memory that no calculation
 * reads and a restart discards. A button that appears to work and does not is
 * worse than no button, so these tests fail if either control comes back.
 */
import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import RuleLibraryView from './RuleLibraryView.jsx';
import * as api from '../api.js';

describe('RuleLibraryView', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchRules').mockResolvedValue({
      rules: [{ code: 'GA_JTC', citation: 'O.C.G.A. § 48-7-40', name: 'Georgia Job Tax Credit', jurisdiction: 'GA', verified: true, one_zero: { thresholds_by_year: {} } }],
    });
  });
  afterEach(() => vi.restoreAllMocks());

  it('lists the authored rule packs', async () => {
    render(<RuleLibraryView />);
    expect(await screen.findByText('Georgia Job Tax Credit')).toBeInTheDocument();
  });

  it('offers no ingestion action that changes nothing the calculation reads', async () => {
    render(<RuleLibraryView />);
    await screen.findByText('Georgia Job Tax Credit');
    expect(screen.queryByRole('button', { name: /re-run ingestion/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /against DCA source/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /confirm & apply/i })).not.toBeInTheDocument();
  });

  it('does not claim values were retrieved rather than authored', async () => {
    render(<RuleLibraryView />);
    await screen.findByText('Georgia Job Tax Credit');
    expect(screen.queryByText(/retrieved with a citation rather than typed in/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/not hand-entered/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Web IQ/i)).not.toBeInTheDocument();
  });

  it('states the authored tax years, and says so when there are none', async () => {
    api.fetchRules.mockResolvedValue({
      rules: [
        { code: 'GA_JTC', citation: 'OCGA § 48-7-40', name: 'Georgia Job Tax Credit', jurisdiction: 'GA', verified: true, version: '0.1.0' },
        { code: 'SC_JTC', citation: 'S.C. Code § 12-6-3360', name: 'South Carolina Jobs Tax Credit', jurisdiction: 'SC', verified: false, version: '0.1.0' },
      ],
    });
    const programs = [
      { program_code: 'GA_JTC', authored_years: [2019, 2020, 2021, 2022, 2023, 2024, 2025] },
      { program_code: 'SC_JTC', authored_years: [] },
    ];
    render(<RuleLibraryView programs={programs} />);
    expect(await screen.findByText('2019\u20132025')).toBeInTheDocument();
    expect(screen.getByText(/no authored years/i)).toBeInTheDocument();
  });

  it('shows no internal build artefacts to an executive reader', async () => {
    api.fetchRules.mockResolvedValue({
      rules: [{ code: 'GA_JTC', citation: 'OCGA § 48-7-40', name: 'Georgia Job Tax Credit', jurisdiction: 'GA', verified: true, version: '0.1.0' }],
    });
    render(<RuleLibraryView programs={[{ program_code: 'GA_JTC', authored_years: [2023] }]} />);
    await screen.findByText('Georgia Job Tax Credit');
    expect(screen.queryByRole('columnheader', { name: 'Version' })).not.toBeInTheDocument();
    expect(screen.queryByText('0.1.0')).not.toBeInTheDocument();
    expect(screen.queryByText(/PROGRAM_CODE_TO_PACK/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\.json/)).not.toBeInTheDocument();
  });
});
