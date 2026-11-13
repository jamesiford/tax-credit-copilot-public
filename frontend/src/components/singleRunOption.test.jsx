/**
 * The opt-in "run as a tracked batch" mode for the single-client controls.
 *
 * Off (the default) the controls behave exactly as before: the existing PositionView tests prove that. On, they queue
 * a one-client batch (forced, because the blocking control always ran) and open its progress page instead of waiting.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import PositionView from './PositionView.jsx';
import { RUN_AS_BATCH_KEY, queueOneClient, runAsBatchEnabled } from '../lib/singleRun.js';
import * as api from '../api.js';

const cell = {
  client_id: 1001, program_code: 'GA_JTC', tax_year: 2023, status: 'assessed', provenance: 'computed',
  provenance_verified: true, identified_usd: '10', claimed_usd: '0', certified_usd: '0', variance_usd: '10',
  opportunity_usd: '10', outcome: 'unclaimed', is_exposure: false,
};
const account = {
  client_id: 1001, cells: [cell], engagements: [],
  totals: { identified_usd: '10', claimed_usd: '0', opportunity_usd: '10', exposure_usd: '0', cells: 1, exposure_cells: 0, unverified_cells: 0 },
};

function Where() {
  const l = useLocation();
  return <span data-testid="where">{l.pathname}</span>;
}

const draw = () => render(
  <MemoryRouter initialEntries={['/c/1001']}>
    <Routes>
      <Route
        path="*"
        element={(
          <>
            <PositionView
              scope={{ clientId: 1001, year: 2023, programCode: null, windowMode: 'single' }}
              scopeWindow={[2023]}
              scopeOptions={{ clients: [{ account_id: 1001, name: 'Sample Client' }] }}
            />
            <Where />
          </>
        )}
      />
    </Routes>
  </MemoryRouter>,
);

beforeEach(() => {
  window.localStorage.clear();
  vi.spyOn(api, 'fetchPortfolioCoverage').mockResolvedValue({ clients: [], totals: {} });
  vi.spyOn(api, 'fetchClientCoverage').mockResolvedValue(account);
  vi.spyOn(api, 'assessClient').mockResolvedValue({ assessed: [], declined: [] });
  vi.spyOn(api, 'startRunBatch').mockResolvedValue({ batch_id: 'one-1' });
});
afterEach(() => { vi.restoreAllMocks(); window.localStorage.clear(); });

describe('run as a tracked batch', () => {
  it('is off by default, so Run assessment blocks and calls the existing endpoint', async () => {
    expect(runAsBatchEnabled()).toBe(false);
    draw();
    await userEvent.click(await screen.findByRole('button', { name: /Run assessment/ }));
    await waitFor(() => expect(api.assessClient).toHaveBeenCalledWith(1001));
    expect(api.startRunBatch).not.toHaveBeenCalled();
    expect(screen.getByTestId('where')).toHaveTextContent('/c/1001');
  });

  it('when on, queues a one-client forced assess batch and opens its progress', async () => {
    window.localStorage.setItem(RUN_AS_BATCH_KEY, '1');
    draw();
    await userEvent.click(await screen.findByRole('button', { name: /Run assessment/ }));
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/runs/one-1'));
    expect(api.assessClient).not.toHaveBeenCalled();
    expect(api.startRunBatch).toHaveBeenCalledWith(expect.objectContaining({
      kind: 'assess', scope: { kind: 'one', client_ids: [1001] }, force: true, tax_years: [], dry_run: false,
      idempotency_key: expect.any(String),
    }));
  });

  it('names the year for a calculation and uses a fresh idempotency key per click', async () => {
    await queueOneClient({ kind: 'calculate', clientId: 7, year: 2024 });
    await queueOneClient({ kind: 'calculate', clientId: 7, year: 2024 });
    const [a, b] = api.startRunBatch.mock.calls.map((c) => c[0]);
    expect(a).toMatchObject({ kind: 'calculate', tax_years: [2024], scope: { kind: 'one', client_ids: [7] } });
    expect(a.idempotency_key).not.toBe(b.idempotency_key);
  });
});
