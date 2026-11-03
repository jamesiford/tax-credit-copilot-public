import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import EmptyState from './EmptyState';

describe('EmptyState', () => {
  it('renders title and explanation in a status region', () => {
    render(
      <EmptyState title="Not calculated yet">
        Nobody has run this client.
      </EmptyState>,
    );
    const region = screen.getByRole('status');
    expect(region).toHaveClass('ui-empty');
    expect(region).toHaveTextContent('Not calculated yet');
    expect(region).toHaveTextContent('Nobody has run this client.');
  });

  it('renders the action node', () => {
    render(
      <EmptyState title="T" action={<button>Run calculation</button>}>
        Why
      </EmptyState>,
    );
    expect(
      screen.getByRole('button', { name: 'Run calculation' }),
    ).toBeInTheDocument();
  });

  it('hides the icon from assistive technology', () => {
    const { container } = render(
      <EmptyState title="T" icon={<svg data-testid="glyph" />}>
        Why
      </EmptyState>,
    );
    expect(container.querySelector('.ui-empty-icon')).toHaveAttribute(
      'aria-hidden',
      'true',
    );
    expect(screen.getByTestId('glyph')).toBeInTheDocument();
  });

  it('omits optional parts that are not supplied', () => {
    const { container } = render(<EmptyState title="Only a title" />);
    expect(container.querySelector('.ui-empty-icon')).toBeNull();
    expect(container.querySelector('.ui-empty-body')).toBeNull();
    expect(container.querySelector('.ui-empty-action')).toBeNull();
  });

  it('renders with only an explanation', () => {
    const { container } = render(<EmptyState>Because filters hide all rows.</EmptyState>);
    expect(container.querySelector('.ui-empty-title')).toBeNull();
    expect(screen.getByRole('status')).toHaveTextContent(
      'Because filters hide all rows.',
    );
  });
});
