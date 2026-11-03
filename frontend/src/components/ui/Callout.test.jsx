import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import Callout from './Callout';

describe('Callout', () => {
  it('renders an aside labelled by its title', () => {
    render(<Callout title="Assessment">Body text</Callout>);
    const aside = screen.getByRole('complementary', { name: 'Assessment' });
    expect(aside).toHaveClass('ui-callout', 'ui-callout-neutral');
    expect(screen.getByText('Body text')).toBeInTheDocument();
  });

  it.each(['neutral', 'above-min', 'below-min', 'partial', 'base-year'])(
    'applies the %s tone',
    (tone) => {
      render(
        <Callout title="T" tone={tone}>
          Body
        </Callout>,
      );
      expect(screen.getByRole('complementary')).toHaveClass(
        `ui-callout-${tone}`,
      );
    },
  );

  it('falls back to neutral for an unknown tone', () => {
    render(
      <Callout title="T" tone="bogus">
        Body
      </Callout>,
    );
    expect(screen.getByRole('complementary')).toHaveClass('ui-callout-neutral');
  });

  it('hides the status dot from assistive technology', () => {
    const { container } = render(<Callout title="T">Body</Callout>);
    expect(container.querySelector('.ui-callout-dot')).toHaveAttribute(
      'aria-hidden',
      'true',
    );
  });

  it('works without a title and leaves the aside unlabelled', () => {
    const { container } = render(<Callout>Only body</Callout>);
    expect(container.querySelector('aside')).not.toHaveAttribute(
      'aria-labelledby',
    );
    expect(container.querySelector('.ui-callout-dot')).toBeNull();
    expect(screen.getByText('Only body')).toBeInTheDocument();
  });
});
