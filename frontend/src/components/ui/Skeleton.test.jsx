import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import Skeleton from './Skeleton';

describe('Skeleton', () => {
  it('renders a busy status region with a hidden loading label', () => {
    render(<Skeleton />);
    const region = screen.getByRole('status');
    expect(region).toHaveAttribute('aria-busy', 'true');
    expect(region).toHaveAttribute('aria-live', 'polite');
    expect(screen.getByText('Loading')).toHaveClass('ui-visually-hidden');
  });

  it('renders three bars by default', () => {
    const { container } = render(<Skeleton />);
    expect(container.querySelectorAll('.ui-skeleton-bar')).toHaveLength(3);
  });

  it('renders the requested number of bars', () => {
    const { container } = render(<Skeleton lines={5} />);
    expect(container.querySelectorAll('.ui-skeleton-bar')).toHaveLength(5);
  });

  it('renders no bars for zero or invalid lines but keeps the label', () => {
    const { container, rerender } = render(<Skeleton lines={0} />);
    expect(container.querySelectorAll('.ui-skeleton-bar')).toHaveLength(0);
    rerender(<Skeleton lines={-2} />);
    expect(container.querySelectorAll('.ui-skeleton-bar')).toHaveLength(0);
    expect(screen.getByText('Loading')).toBeInTheDocument();
  });

  it('hides the bars from assistive technology', () => {
    const { container } = render(<Skeleton lines={2} />);
    container.querySelectorAll('.ui-skeleton-bar').forEach((bar) => {
      expect(bar).toHaveAttribute('aria-hidden', 'true');
    });
  });

  it('accepts a custom label and className', () => {
    render(<Skeleton label="Loading findings" className="extra" />);
    expect(screen.getByText('Loading findings')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveClass('ui-skeleton', 'extra');
  });
});
