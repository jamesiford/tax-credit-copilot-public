import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import FloatingAction, { FLOATING_CLEARANCE_CLASS } from './FloatingAction.jsx';

describe('FloatingAction', () => {
  it('renders a button with the visible label', () => {
    render(<FloatingAction label="Ask Copilot" icon="✦" />);
    const button = screen.getByRole('button', { name: 'Ask Copilot' });
    expect(button).toHaveAttribute('type', 'button');
    expect(button).toHaveClass('ui-floating');
  });

  it('hides the icon from assistive tech', () => {
    const { container } = render(<FloatingAction label="Ask" icon="✦" />);
    expect(container.querySelector('.ui-floating__icon')).toHaveAttribute('aria-hidden', 'true');
  });

  it('omits the icon wrapper without an icon', () => {
    const { container } = render(<FloatingAction label="Ask" />);
    expect(container.querySelector('.ui-floating__icon')).toBeNull();
  });

  it('calls onClick by mouse and keyboard', async () => {
    const onClick = vi.fn();
    render(<FloatingAction label="Ask" onClick={onClick} />);
    await userEvent.click(screen.getByRole('button'));
    await userEvent.keyboard('{Enter}');
    expect(onClick).toHaveBeenCalledTimes(2);
  });

  it('renders an anchor when href is given', () => {
    render(<FloatingAction label="Help" href="/help" />);
    expect(screen.getByRole('link', { name: 'Help' })).toHaveAttribute('href', '/help');
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('passes aria-label and other props through', () => {
    render(<FloatingAction label="Ask" aria-label="Ask Copilot a question" data-testid="fab" />);
    expect(screen.getByRole('button', { name: 'Ask Copilot a question' })).toBe(
      screen.getByTestId('fab'),
    );
  });

  it('exports the clearance class name', () => {
    expect(FLOATING_CLEARANCE_CLASS).toBe('ui-floating-clearance');
  });
});
