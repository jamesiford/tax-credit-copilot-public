import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import ClientHeader from './ClientHeader.jsx';

function Where() {
  const loc = useLocation();
  return <div data-testid="where">{`${loc.pathname}${loc.search}`}</div>;
}

function draw(props = {}) {
  return render(
    <MemoryRouter>
      <ClientHeader clientId={2001} clientName="Cascade" {...props} />
      <Where />
    </MemoryRouter>,
  );
}

describe('the client review header', () => {
  it('has one title, a way back, and the meta values the page holds', () => {
    const onBack = vi.fn();
    draw({
      industry: 'Retail',
      year: 2023,
      method: 'min_max',
      run: { run_id: 'abcdef0123456789', rule_pack_version: 'rules/ga_jtc/2023.json' },
      onBack,
    });
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Cascade');
    const meta = document.querySelector('.ui-meta');
    expect(meta).toHaveTextContent('ClientAccount 2001 · Retail');
    expect(meta).toHaveTextContent('Tax yearTY2023');
    expect(meta).toHaveTextContent('MethodMin-Max');
    expect(meta).toHaveTextContent('Runabcdef012345');
    expect(meta).toHaveTextContent('Rule packga_jtc/2023');
  });

  it('omits a value it does not have rather than showing a bare label', () => {
    draw({ year: 2023 });
    const meta = document.querySelector('.ui-meta');
    expect(meta).not.toHaveTextContent('Run');
    expect(meta).not.toHaveTextContent('Rule pack');
    expect(meta).not.toHaveTextContent('Method');
  });

  it('goes back one drill level', async () => {
    const onBack = vi.fn();
    draw({ onBack });
    await userEvent.click(screen.getByRole('button', { name: /Portfolio/ }));
    expect(onBack).toHaveBeenCalled();
  });

  it('every step is a link and the current one says so', () => {
    draw({ current: 'progress', year: 2023, search: 'year=2023' });
    const flow = within(screen.getByRole('navigation', { name: 'Client review' }));
    expect(flow.getByRole('link', { name: 'At risk' })).toHaveAttribute('aria-current', 'step');
    expect(flow.getByRole('link', { name: 'At risk' })).toHaveAttribute('href', '/c/2001?year=2023&ctab=progress');
    expect(flow.getByRole('link', { name: 'Eligibility' })).toHaveAttribute('href', '/c/2001/eligibility?year=2023');
  });

  it('a step navigates without gating anything', async () => {
    draw({ current: 'location' });
    await userEvent.click(screen.getByRole('link', { name: 'Evidence' }));
    expect(screen.getByTestId('where')).toHaveTextContent('/c/2001/evidence');
  });

  it('says why a step is unavailable, to a screen reader and on the page', () => {
    draw({ clientScope: { payroll_years: [], calculable_years: [] } });
    const flow = within(screen.getByRole('navigation', { name: 'Client review' }));
    expect(flow.queryByRole('link', { name: 'Trend' })).toBeNull();
    expect(flow.getAllByText(/No payroll is held for this client yet/).length).toBeGreaterThan(0);
    expect(screen.getByRole('note')).toHaveTextContent('No payroll is held');
    // The audit trail does not depend on this client having a year.
    expect(flow.getByRole('link', { name: 'Evidence' })).toBeInTheDocument();
  });
});
