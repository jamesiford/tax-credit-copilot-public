/**
 * Selecting clients on the portfolio and starting a batch from it.
 *
 * "Select all N matching" must mean what the screen shows. When the page holds the whole book it is exact (explicit
 * ids); when it does not, it is handed to the server as a filter, and a filter the server cannot express is refused
 * with the reason rather than approximated, because approximating runs clients the person never saw.
 */
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import PortfolioPage from './PortfolioPage.jsx';

vi.mock('../api.js', async () => {
  const actual = await vi.importActual('../api.js');
  return { ...actual, fetchPortfolioV2: vi.fn(), previewRunBatch: vi.fn(), startRunBatch: vi.fn() };
});

const api = await import('../api.js');

const row = (id, name, band, states = ['GA']) => ({
  client_id: id, client_name: name, program_code: 'GA_JTC', tax_year: 2025, priority_band: band, priority_rank: id,
  jobs_margin: 5, identified_usd: '100', claimed_usd: '0', opportunity_usd: '100', states, priceable_states: states,
});
const ROWS = [row(1, 'Alpha Co', 'exposed'), row(2, 'Beta Co', 'settled'), row(3, 'Gamma Co', 'declining', ['SC'])];

const PREVIEW = {
  dry_run: true,
  preview: {
    kind: 'calculate', clients: 3, items: 3, years: 'latest runnable year per client', refresh_once: true, force: false,
    skip_candidates_upper_bound: 0, never_run: 3, manifests_read_for: 3, requires_confirmation: false, confirm_above: 25,
    max_items: 5000, over_size_limit: false, first_items: [], notes: [],
  },
};

function Where() {
  const location = useLocation();
  return <span data-testid="where">{location.pathname}</span>;
}

function draw(total = ROWS.length, search = '') {
  api.fetchPortfolioV2.mockResolvedValue({ total, assessed_clients: 3, unassessed_clients: 0, items: ROWS });
  return render(
    <MemoryRouter initialEntries={[`/${search}`]}>
      <Routes>
        <Route path="*" element={<><PortfolioPage scopeOptions={{ years: { authored: [2025] }, programs: [] }} /><Where /></>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => { window.localStorage.clear(); api.previewRunBatch.mockResolvedValue(PREVIEW); });
afterEach(() => { vi.clearAllMocks(); window.localStorage.clear(); });

describe('selecting on the book', () => {
  it('shows the bar once clients are picked and starts a batch for exactly those', async () => {
    draw();
    await screen.findByRole('button', { name: 'Open Alpha Co' });
    expect(screen.queryByRole('region', { name: 'Selected clients' })).not.toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole('checkbox', { name: 'Select Alpha Co' }));
    await user.click(screen.getByRole('checkbox', { name: 'Select Gamma Co' }));
    expect(screen.getByText('2 clients selected')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Run for 2 clients' }));
    await waitFor(() => expect(api.previewRunBatch).toHaveBeenCalledWith(
      expect.objectContaining({ scope: { kind: 'list', client_ids: [1, 3] }, kind: 'calculate' })));
    api.startRunBatch.mockResolvedValue({ batch_id: 'batch 9' });
    await user.click(await screen.findByRole('button', { name: 'Start 3 runs' }));
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/runs/batch%209'));
    expect(api.startRunBatch).toHaveBeenCalledWith(expect.objectContaining({ idempotency_key: expect.any(String) }));
  });

  it('with the whole book on the page, "select all matching" follows the filters exactly', async () => {
    draw(3, '?bf=state%3AGA');
    await screen.findByRole('button', { name: 'Open Alpha Co' });
    const user = userEvent.setup();
    await user.click(screen.getByRole('checkbox', { name: 'Select Alpha Co' }));
    expect(screen.getByRole('button', { name: /Select all 2 matching/ })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Select all 2 matching/ }));
    expect(screen.getByText('2 clients selected')).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Select Beta Co' }).checked).toBe(true);
    expect(screen.queryByRole('checkbox', { name: 'Select Gamma Co' })).not.toBeInTheDocument();
  });

  it('when the book is larger than the page, "all matching" is a server filter', async () => {
    draw(500, '?bf=band%3Aexposed');
    await screen.findByRole('button', { name: 'Open Alpha Co' });
    const user = userEvent.setup();
    await user.click(screen.getByRole('checkbox', { name: 'Select Alpha Co' }));
    await user.click(screen.getByRole('button', { name: 'Select all matching the filters' }));
    expect(screen.getByText('All clients matching the filters')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Run for the matching clients' }));
    await waitFor(() => expect(api.previewRunBatch).toHaveBeenCalledWith(
      expect.objectContaining({ scope: { kind: 'filter', filter: { band: 'exposed' } } })));
  });

  it('with no filters and a larger book, all matching is every client', async () => {
    draw(500);
    await screen.findByRole('button', { name: 'Open Alpha Co' });
    const user = userEvent.setup();
    await user.click(screen.getByRole('checkbox', { name: 'Select Alpha Co' }));
    await user.click(screen.getByRole('button', { name: 'Select all 500 matching' }));
    await user.click(screen.getByRole('button', { name: 'Run for 500 clients' }));
    await waitFor(() => expect(api.previewRunBatch).toHaveBeenCalledWith(expect.objectContaining({ scope: { kind: 'all' } })));
    expect(await screen.findByText(/every client in the book/)).toBeInTheDocument();
  });

  it('refuses to approximate a filter the server cannot express', async () => {
    draw(500, '?bf=client%3A~beta');
    await screen.findByRole('button', { name: 'Open Beta Co' });
    await userEvent.setup().click(screen.getByRole('checkbox', { name: 'Select Beta Co' }));
    expect(screen.queryByRole('button', { name: /Select all/ })).not.toBeInTheDocument();
    expect(screen.getByText(/cannot be handed to the server/)).toBeInTheDocument();
  });

  it('clears the selection', async () => {
    draw();
    await screen.findByRole('button', { name: 'Open Alpha Co' });
    const user = userEvent.setup();
    await user.click(screen.getByRole('checkbox', { name: 'Select Alpha Co' }));
    await user.click(within(screen.getByRole('region', { name: 'Selected clients' })).getByRole('button', { name: 'Clear' }));
    expect(screen.queryByRole('region', { name: 'Selected clients' })).not.toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Select Alpha Co' }).checked).toBe(false);
  });
});
