/**
 * An employee page opened from a shared URL must resolve without an error.
 *
 * Clicking through from a unit worked; opening the same URL cold 422'd first.
 * The shell's scope holds `year: null` until the client's payroll resolves, and
 * the drill posted immediately with that null. It also re-posted on every shell
 * re-render, because `context` was a fresh object each time and the drill
 * fetches whenever `context` changes identity.
 */
import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import EmployeePage from './EmployeePage.jsx';
import * as api from '../api.js';

const DRILL = {
  basis: 'per_client', record_token: 'tok123', employee_id: 'E1', account_id: 2003,
  state: 'GA', program_code: 'GA_JTC', tax_year: 2022, run: {}, not_available: [],
  raw_source_rows: [], thresholds: { minimum_average_weekly_hours: 35 },
  step1: { min_max: {}, pay_period: {} }, onezero: { months: [], min_max: [], pay_period: [] },
  exceptions: { step1: [], onezero: [] },
};

describe('EmployeePage', () => {
  let drill;
  beforeEach(() => {
    drill = vi.spyOn(api, 'fetchClientEmployeeDrill').mockResolvedValue(DRILL);
  });
  afterEach(() => vi.restoreAllMocks());

  it('waits for a tax year instead of posting the drill without one', async () => {
    const { rerender } = render(<EmployeePage clientId={2003} token="tok123" year={null} />);
    expect(drill).not.toHaveBeenCalled();
    expect(screen.getByText(/Loading the employee calculation/)).toBeInTheDocument();

    rerender(<EmployeePage clientId={2003} token="tok123" year={2022} />);
    expect(await screen.findByText('E1')).toBeInTheDocument();
    expect(drill).toHaveBeenCalledTimes(1);
    expect(drill.mock.calls[0][0]).toMatchObject({ recordToken: 'tok123', taxYear: 2022, accountId: 2003 });
  });

  it('does not re-post the drill when the shell re-renders with the same scope', async () => {
    const { rerender } = render(<EmployeePage clientId={2003} token="tok123" year={2022} />);
    await screen.findByText('E1');
    rerender(<EmployeePage clientId={2003} token="tok123" year={2022} clientName="Ironbridge" />);
    rerender(<EmployeePage clientId={2003} token="tok123" year={2022} clientName="Ironbridge" />);
    expect(drill).toHaveBeenCalledTimes(1);
  });

  it('opens the sealed run when no client is named', async () => {
    const sealed = vi.spyOn(api, 'fetchWorkspaceEmployee').mockResolvedValue({ ...DRILL, basis: 'sealed' });
    render(<EmployeePage clientId={null} token="tok123" year={null} />);
    await screen.findByText('E1');
    expect(sealed).toHaveBeenCalledWith('tok123');
    expect(drill).not.toHaveBeenCalled();
  });

  it('adds the employee to the What-if stack from the walk, and opens it (29 Sep)', async () => {
    const store = await import('../lib/whatIfStack.js');
    const data = new Map();
    store.setStackStorage({ getItem: (k) => data.get(k) ?? null, setItem: (k, v) => data.set(k, v), removeItem: (k) => data.delete(k) });
    drill.mockResolvedValue({
      ...DRILL, tax_year: 2026,
      rest_of_year: { state: 'open', additional_weekly_hours: 2.5 },
      where: { worksite_id: 'GA_GA-002' },
      step1: { min_max: { avg_weekly_hours: 33, avg_weekly_wages: 900 }, pay_period: {} },
    });
    const onOpenWhatIf = vi.fn();
    render(<EmployeePage clientId={2003} token="tok123" year={2026} onOpenWhatIf={onOpenWhatIf} />);

    const add = await screen.findByRole('button', { name: /Add to What-if/ });
    expect(add).toHaveAttribute('title', expect.stringContaining('+2.5 hrs/wk'));
    add.click();
    expect(await screen.findByRole('button', { name: /In the What-if stack/ })).toBeInTheDocument();
    expect(store.readStack({ clientId: 2003, taxYear: 2026, method: 'min_max' })).toEqual([{ token: 'tok123', hours: 2.5, raise: 0 }]);

    screen.getByRole('button', { name: /Project in What-if/ }).click();
    expect(onOpenWhatIf).toHaveBeenCalledWith(expect.stringMatching(/^\/c\/2003\?ctab=whatif&wstack=tok123%7E2\.5%7E0&wyear=2026&wmethod=min_max&wrun=1$/));
  });

  it('says why an employee on pace or in a closed year cannot be added', async () => {
    drill.mockResolvedValue({ ...DRILL, rest_of_year: { state: 'closed' } });
    render(<EmployeePage clientId={2003} token="tok123" year={2022} />);
    const add = await screen.findByRole('button', { name: /Add to What-if/ });
    expect(add).toBeDisabled();
    expect(add).toHaveAttribute('title', expect.stringMatching(/year is closed/));
  });
});