import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import SectionHeading from './SectionHeading';

describe('SectionHeading', () => {
  it('renders an h2 by default', () => {
    render(<SectionHeading>Locations</SectionHeading>);
    const heading = screen.getByRole('heading', { level: 2 });
    expect(heading).toHaveClass('ui-section-heading');
    expect(heading).toHaveTextContent('Locations');
  });

  it.each([2, 3, 4])('renders level %i', (level) => {
    render(<SectionHeading level={level}>Title</SectionHeading>);
    expect(screen.getByRole('heading', { level })).toBeInTheDocument();
  });

  it('falls back to h2 for an unsupported level', () => {
    render(<SectionHeading level={6}>Title</SectionHeading>);
    expect(screen.getByRole('heading', { level: 2 })).toBeInTheDocument();
  });

  it('renders the count in parentheses', () => {
    render(<SectionHeading count={12}>Findings</SectionHeading>);
    expect(screen.getByRole('heading')).toHaveTextContent('Findings (12)');
    expect(screen.getByText('(12)')).toHaveClass('ui-section-heading-count');
  });

  it('renders a zero count', () => {
    render(<SectionHeading count={0}>Findings</SectionHeading>);
    expect(screen.getByRole('heading')).toHaveTextContent('Findings (0)');
  });

  it('omits the count when not supplied', () => {
    const { container } = render(<SectionHeading>Findings</SectionHeading>);
    expect(container.querySelector('.ui-section-heading-count')).toBeNull();
  });

  it('merges a custom className', () => {
    render(<SectionHeading className="extra">T</SectionHeading>);
    expect(screen.getByRole('heading')).toHaveClass(
      'ui-section-heading',
      'extra',
    );
  });
});
