import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import CountBadge from './CountBadge';

describe('CountBadge', () => {
  it('shows the count with a labelled accessible name', () => {
    render(<CountBadge count={7} label="open findings" />);
    const badge = screen.getByLabelText('7 open findings');
    expect(badge).toHaveClass('ui-count-badge');
    expect(badge).toHaveTextContent('7');
  });

  it('caps visible text at 99+ but keeps the full count in the label', () => {
    render(<CountBadge count={250} label="open findings" />);
    const badge = screen.getByLabelText('250 open findings');
    expect(badge).toHaveTextContent('99+');
  });

  it('does not cap at exactly max', () => {
    render(<CountBadge count={99} label="items" />);
    expect(screen.getByLabelText('99 items')).toHaveTextContent('99');
    expect(screen.getByLabelText('99 items')).not.toHaveTextContent('99+');
  });

  it('honours a custom max', () => {
    render(<CountBadge count={12} max={9} label="items" />);
    expect(screen.getByLabelText('12 items')).toHaveTextContent('9+');
  });

  it('renders nothing for zero by default', () => {
    const { container } = render(<CountBadge count={0} label="items" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders zero when showZero is set', () => {
    render(<CountBadge count={0} label="items" showZero />);
    expect(screen.getByLabelText('0 items')).toHaveTextContent('0');
  });

  it('renders nothing for a non-numeric count', () => {
    const { container } = render(<CountBadge count={undefined} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('falls back to the bare number when no label is given', () => {
    render(<CountBadge count={3} />);
    expect(screen.getByLabelText('3')).toBeInTheDocument();
  });
});
