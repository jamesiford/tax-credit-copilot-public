/**
 * Selecting clients and starting a batch: the bar, the grid's checkboxes and the dialog.
 *
 * The behaviours that matter here fail quietly if they are wrong: a preview that is skipped, a skip count that reads
 * as a promise, a double click that queues twice, a confirmation that does not have to be typed, a refusal that
 * says nothing about what to change.
 */
import { act, render, screen, waitFor, within } from '@testing-library/react';
import { useState } from 'react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import BookGrid from '../BookGrid.jsx';
import RunDialog from './RunDialog.jsx';
import SelectionBar from './SelectionBar.jsx';
import { emptySelection, setPage, toggleId } from '../../lib/runBatches.js';

vi.mock('../../api.js', async () => {
  const actual = await vi.importActual('../../api.js');
  return { ...actual, previewRunBatch: vi.fn(), startRunBatch: vi.fn(), fetchClientCoverage: vi.fn() };
});

const api = await import('../../api.js');

const PREVIEW = {
  dry_run: true,
  preview: {
    kind: 'calculate', clients: 3, items: 3, years: 'latest runnable year per client', refresh_once: true, force: false,
    skip_unchanged: true, skip_coverage: 'all_years', programs: { GA_JTC: 3 }, multi_program_clients: 0,
    per_client_year_items: false, skip_candidates_upper_bound: 2, never_run: 1, manifests_read_for: 3,
    requires_confirmation: false, confirm_above: 25, max_items: 5000, over_size_limit: false,
    first_items: [
      { client_id: 1, client_name: 'Alpha Co', last_run: { state: 'never_run' } },
      { client_id: 2, client_name: 'Beta Co', last_run: { state: 'has_run', tax_year: 2025, completed_at: '2026-02-01T10:00:00Z' } },
    ],
    notes: ['Whether a client is skipped as unchanged is decided when its item starts; this is an upper bound, not a promise.'],
  },
};

afterEach(() => vi.clearAllMocks());

const ROWS = [
  { client_id: 1, client_name: 'Alpha Co', priority_band: 'exposed', program_code: 'GA_JTC', tax_year: 2025, identified_usd: '10', states: ['GA'] },
  { client_id: 2, client_name: 'Beta Co', priority_band: 'settled', program_code: 'GA_JTC', tax_year: 2025, identified_usd: '0', states: ['GA'] },
  { client_id: 3, client_name: 'Gamma Co', priority_band: 'declining', program_code: 'GA_JTC', tax_year: 2025, identified_usd: '5', states: ['SC'] },
];

function Grid({ initial = emptySelection() }) {
  const [sel, setSel] = useState(initial);
  return (
    <BookGrid
      rows={ROWS} filters={{}} onFilter={() => {}} sort={null} onSort={() => {}}
      selection={sel}
      onToggleRow={(id) => setSel((cur) => toggleId(cur, id))}
      onTogglePage={(ids, on) => setSel((cur) => setPage(cur, ids, on))}
    />
  );
}

describe('selecting rows in the book', () => {
  it('has a labelled checkbox per client and one for the page, with an indeterminate middle state', async () => {
    render(<Grid />);
    const user = userEvent.setup();
    const page = screen.getByRole('checkbox', { name: 'Select all 3 clients on this page' });
    expect(page.checked).toBe(false);
    await user.click(screen.getByRole('checkbox', { name: 'Select Alpha Co' }));
    expect(page.indeterminate).toBe(true);
    await user.click(page);
    expect(screen.getByRole('checkbox', { name: 'Select Gamma Co' }).checked).toBe(true);
    expect(page.checked).toBe(true);
    await user.click(page);
    expect(screen.getByRole('checkbox', { name: 'Select Alpha Co' }).checked).toBe(false);
  });

  it('is operable by keyboard alone', async () => {
    render(<Grid />);
    const user = userEvent.setup();
    const row = screen.getByRole('checkbox', { name: 'Select Beta Co' });
    row.focus();
    await user.keyboard(' ');
    expect(row.checked).toBe(true);
  });

  it('renders no checkboxes when selection is not wired (the grid is unchanged for every other caller)', () => {
    render(<BookGrid rows={ROWS} filters={{}} onFilter={() => {}} sort={null} onSort={() => {}} />);
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
  });
});

describe('the selection bar', () => {
  const sel = { ids: [1, 2], matching: null };

  it('shows nothing until something is selected and announces the count', () => {
    const { rerender } = render(<SelectionBar selection={emptySelection()} onClear={() => {}} onRun={() => {}} />);
    expect(screen.queryByRole('region', { name: 'Selected clients' })).not.toBeInTheDocument();
    rerender(<SelectionBar selection={sel} onClear={() => {}} onRun={() => {}} />);
    expect(screen.getByRole('status')).toHaveTextContent('2 clients selected');
    expect(screen.getByRole('button', { name: /Run for 2 clients/ })).toBeInTheDocument();
  });

  it('offers "select all N matching" and says why when it cannot be handed to the server', async () => {
    const onAll = vi.fn();
    const { rerender } = render(
      <SelectionBar selection={sel} matching={{ ok: true, count: 240 }} onSelectMatching={onAll} onClear={() => {}} onRun={() => {}} />,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Select all 240 matching' }));
    expect(onAll).toHaveBeenCalled();
    rerender(
      <SelectionBar selection={sel} matching={{ ok: false, count: null, reason: 'The client filter cannot be handed to the server.' }} onClear={() => {}} onRun={() => {}} />,
    );
    expect(screen.queryByRole('button', { name: /Select all/ })).not.toBeInTheDocument();
    expect(screen.getByText(/cannot be handed to the server/)).toBeInTheDocument();
  });

  it('describes a server group whose size is only known at preview', () => {
    render(<SelectionBar selection={{ ids: [], matching: { count: null, filter: { band: 'exposed' } } }} onClear={() => {}} onRun={() => {}} />);
    expect(screen.getByRole('status')).toHaveTextContent('All clients matching the filters');
    expect(screen.getByRole('button', { name: 'Run for the matching clients' })).toBeInTheDocument();
  });
});

const open = (props = {}) => render(
  <RunDialog
    open selection={{ ids: [1, 2, 3], matching: null }} onClose={() => {}} onStarted={() => {}}
    scopeOptions={{ years: { authored: [2024, 2025] }, programs: [{ program_code: 'GA_JTC', name: 'Georgia JTC', authored_years: [2025] }] }}
    {...props}
  />,
);

describe('the start dialog', () => {
  it('previews first: Start is disabled while the preview loads and until it has answered', async () => {
    let release;
    api.previewRunBatch.mockReturnValue(new Promise((r) => { release = r; }));
    open();
    expect(screen.getByRole('button', { name: /^Start/ })).toBeDisabled();
    expect(screen.getByText('Previewing what would run')).toBeInTheDocument();
    await act(async () => { release(PREVIEW); });
    expect(await screen.findByRole('button', { name: 'Start 3 runs' })).toBeEnabled();
    expect(api.startRunBatch).not.toHaveBeenCalled();
  });

  it('states skips as an upper bound and never as a promise', async () => {
    api.previewRunBatch.mockResolvedValue(PREVIEW);
    open();
    expect(await screen.findByText(/Up to 2 may be skipped as unchanged/)).toBeInTheDocument();
    expect(screen.getByText(/upper bound: it is decided when each run starts/)).toBeInTheDocument();
    expect(screen.getByText(/One run per client refreshes every year/)).toBeInTheDocument();
    expect(screen.getByText('Never calculated')).toBeInTheDocument();
  });

  it('previews again, with the new options, when an option changes', async () => {
    api.previewRunBatch.mockResolvedValue(PREVIEW);
    open();
    await screen.findByText(/Up to 2/);
    const skip = screen.getByRole('checkbox', { name: /Skip clients whose data and rules are unchanged/ });
    expect(skip).not.toBeChecked();
    await userEvent.click(skip);
    await waitFor(() => expect(api.previewRunBatch).toHaveBeenLastCalledWith(expect.objectContaining({ skip_unchanged: true })));
    await userEvent.click(screen.getByRole('radio', { name: /Assess/ }));
    await waitFor(() => expect(api.previewRunBatch).toHaveBeenLastCalledWith(expect.objectContaining({ kind: 'assess', skip_unchanged: true })));
  });

  it('turns on one-run-per-client-and-year only once years are chosen, and says the cost multiplies', async () => {
    api.previewRunBatch.mockImplementation(async (body) => ({
      ...PREVIEW, preview: { ...PREVIEW.preview, refresh_once: body.refresh_once },
    }));
    open();
    await screen.findByText(/Up to 2/);
    const perYear = screen.getByRole('checkbox', { name: /One run per client and year/ });
    expect(perYear).toBeDisabled();
    await userEvent.click(screen.getByRole('checkbox', { name: 'TY2024' }));
    await userEvent.click(screen.getByRole('checkbox', { name: 'TY2025' }));
    expect(perYear).toBeEnabled();
    await userEvent.click(perYear);
    await waitFor(() => expect(api.previewRunBatch).toHaveBeenLastCalledWith(
      expect.objectContaining({ tax_years: [2024, 2025], refresh_once: false })));
    expect(await screen.findByText(/multiplied by the number of years/)).toBeInTheDocument();
  });

  it('starts with one idempotency key, so a double click is one request', async () => {
    api.previewRunBatch.mockResolvedValue(PREVIEW);
    let release;
    api.startRunBatch.mockReturnValue(new Promise((r) => { release = r; }));
    const onStarted = vi.fn();
    open({ onStarted });
    const start = await screen.findByRole('button', { name: 'Start 3 runs' });
    await userEvent.dblClick(start);
    expect(api.startRunBatch).toHaveBeenCalledTimes(1);
    const sent = api.startRunBatch.mock.calls[0][0];
    expect(sent.idempotency_key).toBeTruthy();
    expect(sent).toMatchObject({ kind: 'calculate', scope: { kind: 'list', client_ids: [1, 2, 3] }, dry_run: false });
    await act(async () => { release({ batch_id: 'b1' }); });
    expect(onStarted).toHaveBeenCalledWith({ batch_id: 'b1' });
  });

  it('requires the item count to be typed above the threshold, and sends it', async () => {
    api.previewRunBatch.mockResolvedValue({ ...PREVIEW, preview: { ...PREVIEW.preview, items: 40, clients: 40, requires_confirmation: true } });
    api.startRunBatch.mockResolvedValue({ batch_id: 'b2' });
    open();
    const start = await screen.findByRole('button', { name: 'Start 40 runs' });
    expect(start).toBeDisabled();
    const box = screen.getByRole('textbox', { name: 'Type 40 to confirm' });
    await userEvent.type(box, '4');
    expect(start).toBeDisabled();
    await userEvent.type(box, '0');
    expect(start).toBeEnabled();
    await userEvent.click(start);
    expect(api.startRunBatch).toHaveBeenCalledWith(expect.objectContaining({ confirm_items: 40 }));
  });

  it('flags an all-clients scope, and a selection over the size limit cannot start', async () => {
    api.previewRunBatch.mockResolvedValue({ ...PREVIEW, preview: { ...PREVIEW.preview, items: 9000, over_size_limit: true, max_items: 5000 } });
    open({ selection: { ids: [], matching: { count: 9000, filter: {} } } });
    expect(await screen.findByText(/every client in the book/)).toBeInTheDocument();
    expect(screen.getByText(/Narrow the selection/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Start/ })).toBeDisabled();
  });

  it('lists unavailable clients with the reason, never as "not assessed"', async () => {
    api.previewRunBatch.mockResolvedValue({ ...PREVIEW, preview: { ...PREVIEW.preview, unavailable: [{ client_id: 3, client_name: 'Gamma Co', dependency: 'claims_store', reason: 'the claim store could not be read' }] } });
    open();
    expect(await screen.findByText('1 unavailable')).toBeInTheDocument();
    expect(screen.getByText(/Gamma Co: the claim store could not be read/)).toBeInTheDocument();
    expect(screen.queryByText(/not assessed$/)).not.toBeInTheDocument();
  });

  it('shows the API\u2019s own reason and remedy when the preview or the start is refused', async () => {
    const refused = Object.assign(new Error('x'), { reason: 'These clients are not in the client book: 999.', remedy: 'Remove them or check the ids.' });
    api.previewRunBatch.mockRejectedValue(refused);
    open();
    expect(await screen.findByText('The preview is unavailable')).toBeInTheDocument();
    expect(screen.getByText('These clients are not in the client book: 999.')).toBeInTheDocument();
    expect(screen.getByText(/Remove them or check the ids\. Nothing was changed\./)).toBeInTheDocument();
  });

  it('keeps the dialog open and says what to change when a start is refused', async () => {
    api.previewRunBatch.mockResolvedValue(PREVIEW);
    api.startRunBatch.mockRejectedValue(Object.assign(new Error('x'), { reason: 'The worker store is down.', remedy: 'Try again in a minute.' }));
    open();
    await userEvent.click(await screen.findByRole('button', { name: 'Start 3 runs' }));
    expect(await screen.findByText('Not started')).toBeInTheDocument();
    expect(screen.getByText('Try again in a minute.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Start 3 runs' })).toBeEnabled();
  });

  it('is a modal dialog that closes on Escape', async () => {
    api.previewRunBatch.mockResolvedValue(PREVIEW);
    const onClose = vi.fn();
    open({ onClose });
    const dialog = await screen.findByRole('dialog', { name: /Run for 3 clients/ });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    await userEvent.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalled();
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
  });
});

describe('the start dialog with several programs in one state', () => {
  const several = {
    years: { authored: [2025] },
    programs: [
      { program_code: 'ZZ_ALPHA_JTC', name: 'Alpha credit', authored_years: [2025], jurisdiction: { code: 'ZZ' } },
      { program_code: 'ZZ_BETA_JTC', name: 'Beta credit', authored_years: [2025], jurisdiction: { code: 'ZZ' } },
      { program_code: 'GA_JTC', name: 'Georgia JTC', authored_years: [2025], jurisdiction: { code: 'GA' } },
    ],
  };

  it('names the program by code where two share a state, and by name where one does not', async () => {
    api.previewRunBatch.mockResolvedValue(PREVIEW);
    open({ scopeOptions: several });
    const select = await screen.findByLabelText('Program');
    const labels = [...select.querySelectorAll('option')].map((o) => o.textContent);
    expect(labels).toEqual(expect.arrayContaining(['Alpha credit (ZZ_ALPHA_JTC)', 'Beta credit (ZZ_BETA_JTC)', 'Georgia JTC']));
  });

  it('starts the batch for the chosen program', async () => {
    api.previewRunBatch.mockResolvedValue(PREVIEW);
    api.startRunBatch.mockResolvedValue({ batch_id: 'b1' });
    open({ scopeOptions: several });
    await userEvent.selectOptions(await screen.findByLabelText('Program'), 'ZZ_BETA_JTC');
    await waitFor(() => expect(api.previewRunBatch).toHaveBeenLastCalledWith(expect.objectContaining({ program_code: 'ZZ_BETA_JTC' })));
    const start = await screen.findByRole('button', { name: 'Start 3 runs' });
    await waitFor(() => expect(start).toBeEnabled());
    await userEvent.click(start);
    await waitFor(() => expect(api.startRunBatch).toHaveBeenCalledWith(expect.objectContaining({ program_code: 'ZZ_BETA_JTC' })));
  });
});
