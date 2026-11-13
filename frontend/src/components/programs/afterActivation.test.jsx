/**
 * After activation: a program that becomes calculable shows up in the catalog, the run dialog and the program helpers with no
 * frontend change. The only input is the data the API already returns (`/api/scope` programs and `/api/v2/programs`), carrying
 * the fictional program; no component names a program code. [F05.9]
 */
import { act, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import RunDialog from '../runs/RunDialog.jsx';
import ProgramCatalog from './ProgramCatalog.jsx';
import { calculablePrograms, programsInState } from '../../lib/programChoice.js';

vi.mock('../../api.js', async () => {
  const actual = await vi.importActual('../../api.js');
  return { ...actual, previewRunBatch: vi.fn().mockResolvedValue({ dry_run: true, preview: { kind: 'calculate', clients: 1, items: 1, requires_confirmation: false, first_items: [], notes: [], programs: {}, multi_program_clients: 0 } }), startRunBatch: vi.fn() };
});

afterEach(() => vi.clearAllMocks());

const FICTIONAL = {
  program_code: 'ZZ_DEMO_JTC', name: 'Fictional Demo Credit', authored_years: [2024, 2025], placeholder_years: [2024, 2025],
  jurisdiction: { level: 'state', code: 'ZZ' }, calculable: true,
};
const DESCRIBED = { program_code: 'YY_DESCRIBED_ONLY', name: 'Described Only', authored_years: [], jurisdiction: { level: 'state', code: 'YY' }, calculable: false };
const GEORGIA = { program_code: 'GA_JTC', name: 'Georgia Jobs Tax Credit', authored_years: [2024], jurisdiction: { level: 'state', code: 'GA' }, calculable: true };

const scopeOptions = (programs) => ({ years: { authored: [2024, 2025] }, programs });

describe('the helpers that every control reads', () => {
  it('offers the activated program as calculable and as the one program of its state', () => {
    const options = scopeOptions([GEORGIA, DESCRIBED, FICTIONAL]);
    expect(calculablePrograms(options).map((p) => p.program_code)).toEqual(['GA_JTC', 'ZZ_DEMO_JTC']);
    expect(programsInState(options, 'zz').map((p) => p.program_code)).toEqual(['ZZ_DEMO_JTC']);
  });

  it('does not offer it before activation, and never offers a described program', () => {
    expect(calculablePrograms(scopeOptions([GEORGIA, DESCRIBED])).map((p) => p.program_code)).toEqual(['GA_JTC']);
  });
});

describe('the run dialog', () => {
  const dialog = (programs) => render(
    <RunDialog open selection={{ ids: [1], matching: null }} onClose={() => {}} onStarted={() => {}} scopeOptions={scopeOptions(programs)} />,
  );

  it('lists the activated program as a selectable program with no code change', async () => {
    dialog([GEORGIA, DESCRIBED, FICTIONAL]);
    await act(async () => {});
    const select = screen.getByLabelText('Program');
    const options = within(select).getAllByRole('option').map((o) => o.value);
    expect(options).toContain('ZZ_DEMO_JTC');
    expect(options).not.toContain('YY_DESCRIBED_ONLY');
    expect(within(select).getByRole('option', { name: 'Fictional Demo Credit' })).toBeInTheDocument();
  });

  it('does not list it before the program is activated', async () => {
    dialog([GEORGIA, DESCRIBED]);
    await act(async () => {});
    expect(within(screen.getByLabelText('Program')).queryByRole('option', { name: 'Fictional Demo Credit' })).toBeNull();
  });
});

describe('the catalog', () => {
  const rows = (calculable) => [{
    code: 'ZZ_DEMO_JTC', name: 'Fictional Demo Credit', state: 'ZZ', jurisdiction: { level: 'state', code: 'ZZ' },
    lifecycle: calculable ? 'calculable' : 'described', authored_years: calculable ? [2024, 2025] : [], unverified_years: calculable ? [2024, 2025] : [],
    verification: 'not_verified', calculable, not_calculable_reason: calculable ? '' : 'No year-scoped rule packs authored for ZZ_DEMO_JTC.',
    engagement: { in_scope: 0, out_of_scope: 0, prospective: 0, clients: 0 },
  }];

  it('shows the program as described and not calculable until its years are authored', () => {
    render(<ProgramCatalog rows={rows(false)} onOpen={() => {}} />);
    expect(screen.getByText('Described, not calculable')).toBeInTheDocument();
    expect(screen.getByText(/No year-scoped rule packs authored for ZZ_DEMO_JTC/)).toBeInTheDocument();
  });

  it('shows it as calculable for exactly its authored years, still not verified, once they are', () => {
    render(<ProgramCatalog rows={rows(true)} onOpen={() => {}} />);
    const table = screen.getByRole('table', { name: 'Program catalog' });
    expect(within(table).getAllByText('Calculable').length).toBeGreaterThan(1);
    expect(within(table).getByText('2024\u20132025')).toBeInTheDocument();
    expect(within(table).getByText('Not verified: 2 of 2 years flagged')).toBeInTheDocument();
  });
});
