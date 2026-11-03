import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import Button from './Button.jsx';

describe('Button', () => {
  it('renders every variant with its own class', () => {
    for (const variant of ['primary', 'secondary', 'ghost', 'link', 'danger']) {
      const { unmount } = render(<Button variant={variant}>Go</Button>);
      expect(screen.getByRole('button', { name: 'Go' })).toHaveClass('ui-btn', `ui-btn-${variant}`);
      unmount();
    }
  });

  it('falls back to secondary for an unknown variant rather than rendering unstyled', () => {
    render(<Button variant="neon">Go</Button>);
    expect(screen.getByRole('button')).toHaveClass('ui-btn-secondary');
  });

  it('supports a small size and an icon that is hidden from assistive tech', () => {
    render(<Button size="sm" icon={<svg data-testid="i" />}>Save</Button>);
    expect(screen.getByRole('button')).toHaveClass('ui-btn-sm');
    expect(screen.getByTestId('i').parentElement).toHaveAttribute('aria-hidden', 'true');
  });

  it('is a real button that fires on click and on the keyboard', async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Run</Button>);
    await userEvent.click(screen.getByRole('button'));
    screen.getByRole('button').focus();
    await userEvent.keyboard('{Enter}');
    expect(onClick).toHaveBeenCalledTimes(2);
  });

  it('does not fire while disabled or loading, and says it is busy', async () => {
    const onClick = vi.fn();
    const { rerender } = render(<Button disabled onClick={onClick}>Run</Button>);
    await userEvent.click(screen.getByRole('button'));
    rerender(<Button loading onClick={onClick}>Run</Button>);
    await userEvent.click(screen.getByRole('button'));
    expect(onClick).not.toHaveBeenCalled();
    expect(screen.getByRole('button')).toBeDisabled();
    expect(screen.getByRole('button')).toHaveAttribute('aria-busy', 'true');
  });

  it('renders a link with the same look when given an href', () => {
    render(<Button href="/rules" variant="link">Rules</Button>);
    const link = screen.getByRole('link', { name: 'Rules' });
    expect(link).toHaveAttribute('href', '/rules');
    expect(link).toHaveClass('ui-btn-link');
  });

  it('defaults to type=button so it never submits a form by accident', () => {
    render(<Button>Go</Button>);
    expect(screen.getByRole('button')).toHaveAttribute('type', 'button');
  });
});
