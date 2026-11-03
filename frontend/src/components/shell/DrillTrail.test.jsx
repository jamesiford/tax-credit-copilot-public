import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import DrillTrail from './DrillTrail.jsx';

const handlers = () => ({
  onOpenPortfolio: vi.fn(), onOpenClient: vi.fn(), onOpenUnit: vi.fn(), onSelectView: vi.fn(),
});
const trail = () => screen.getByRole('navigation', { name: 'Where you are' });

describe('DrillTrail', () => {
  it('at the book, is one quiet line that says what to do next', () => {
    render(<DrillTrail clientId="portfolio" view="trend" {...handlers()} />);
    expect(within(trail()).getByText('Portfolio')).toBeInTheDocument();
    expect(within(trail()).getByText(/choose a client to drill in/)).toBeInTheDocument();
    expect(within(trail()).queryAllByRole('button')).toHaveLength(0);
    expect(within(trail()).queryByText('Employee')).not.toBeInTheDocument();
  });

  it('at a client, names it, marks it current, and dims what is not reached', () => {
    render(<DrillTrail clientId={2001} clientName="Cascade Retail" view="trend" {...handlers()} />);
    const nav = trail();
    expect(within(nav).getByText('Cascade Retail').closest('li')).toHaveAttribute('aria-current', 'page');
    // Reached and not current -> a button.
    expect(within(nav).getByRole('button', { name: 'Portfolio' })).toBeInTheDocument();
    // Not reached -> text with a hint, never a disabled button.
    expect(within(nav).getByText('Location').closest('li')).toHaveClass('pending');
    expect(within(nav).queryByRole('button', { name: 'Location' })).not.toBeInTheDocument();
    expect(within(nav).getByText('open a year on a location')).toBeInTheDocument();
    expect(within(nav).queryByRole('button', { name: 'Employee' })).not.toBeInTheDocument();
  });

  it('the current rung is not a button: you are already there', () => {
    render(<DrillTrail clientId={2001} clientName="Cascade Retail" view="trend" {...handlers()} />);
    expect(within(trail()).queryByRole('button', { name: 'Cascade Retail' })).not.toBeInTheDocument();
  });

  it('at a location, the client and the book are buttons and the location is current', async () => {
    const h = handlers();
    render(<DrillTrail clientId={2001} clientName="Cascade Retail" unitId="GA_GA-001" view="trend" {...h} />);
    const nav = trail();
    expect(within(nav).getByText('GA_GA-001').closest('li')).toHaveAttribute('aria-current', 'page');
    await userEvent.click(within(nav).getByRole('button', { name: 'Cascade Retail' }));
    expect(h.onOpenClient).toHaveBeenCalled();
    await userEvent.click(within(nav).getByRole('button', { name: 'Portfolio' }));
    expect(h.onOpenPortfolio).toHaveBeenCalled();
  });

  it('at an employee, every rung above is reached and only Employee is current', async () => {
    const h = handlers();
    render(<DrillTrail
      clientId={2001} clientName="Cascade Retail" unitId="GA_GA-001" token="tok" view="trend" {...h}
    />);
    const nav = trail();
    expect(within(nav).getByText('Employee').closest('li')).toHaveAttribute('aria-current', 'page');
    expect(within(nav).getByRole('button', { name: 'GA_GA-001' })).toBeInTheDocument();
    await userEvent.click(within(nav).getByRole('button', { name: 'GA_GA-001' }));
    expect(h.onOpenUnit).toHaveBeenCalled();
    expect(nav.querySelectorAll('[aria-current="page"]')).toHaveLength(1);
  });

  it('on Eligibility, that rung is current and the client rung leads back', async () => {
    const h = handlers();
    render(<DrillTrail clientId={2001} clientName="Cascade Retail" view="eligibility" {...h} />);
    const nav = trail();
    expect(within(nav).getByText('Eligibility').closest('li')).toHaveAttribute('aria-current', 'page');
    await userEvent.click(within(nav).getByRole('button', { name: 'Cascade Retail' }));
    expect(h.onOpenClient).toHaveBeenCalled();
  });

  it('on the client page, Eligibility is reached and leads to the view', async () => {
    const h = handlers();
    render(<DrillTrail clientId={2001} clientName="Cascade Retail" view="trend" {...h} />);
    await userEvent.click(within(trail()).getByRole('button', { name: 'Eligibility' }));
    expect(h.onSelectView).toHaveBeenCalledWith('eligibility');
  });
});
