/**
 * An empty answer is not an answer.
 *
 * The forced-states check (tools/check_states.py) made every endpoint answer 200
 * with `{}`. Three views then crashed or drew `undefined`: a response with the
 * right status and none of the shape they read. Each now says the answer held
 * nothing, and says nothing was changed, instead of reading a field off it.
 */
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api.js';
import AgentActivityView from './AgentActivityView.jsx';
import DataIngestionView from './DataIngestionView.jsx';
import EmployeeDrill from './EmployeeDrill.jsx';

afterEach(() => vi.restoreAllMocks());

describe('an empty body from the API', () => {
  it('Payroll data says it is unavailable', async () => {
    vi.spyOn(api, 'fetchIngestion').mockResolvedValue({});
    vi.spyOn(api, 'fetchIngestionRows').mockResolvedValue({ rows: [], total: 0 });
    render(<DataIngestionView taxYear={2023} accountId={2001} />);
    expect(await screen.findByText('Payroll data is unavailable')).toBeInTheDocument();
    expect(screen.getByText(/Nothing was changed/)).toBeInTheDocument();
  });

  it('Agents says findings are unavailable and still renders the page', async () => {
    vi.spyOn(api, 'fetchFindings').mockResolvedValue({});
    vi.spyOn(api, 'fetchMe').mockResolvedValue({});
    render(<AgentActivityView scope={{ clientId: 2001, year: 2023, programCode: 'GA_JTC' }} scopeOptions={{ programs: [] }} />);
    expect(await screen.findByText('Findings are unavailable')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Agents' })).toBeInTheDocument();
  });

  it('the employee walk says it holds no calculation, not "undefined"', async () => {
    vi.spyOn(api, 'fetchClientEmployeeDrill').mockResolvedValue({});
    render(<EmployeeDrill recordToken="tok" context={{ taxYear: 2023, state: 'GA', accountId: 2001 }} />);
    expect(await screen.findByText(/calculation is unavailable/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/undefined/);
  });
});
