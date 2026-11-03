import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import Pill from './Pill';

const VARIANTS = [
  'above-min',
  'below-min',
  'base-year',
  'partial',
  'neutral',
  'info',
  'category',
];

describe('Pill', () => {
  it('renders children with neutral soft defaults', () => {
    render(<Pill>Pending</Pill>);
    const pill = screen.getByText('Pending');
    expect(pill).toHaveClass('ui-pill', 'ui-pill-neutral', 'ui-pill-soft');
  });

  it.each(VARIANTS)('applies the %s variant', (variant) => {
    render(<Pill variant={variant}>Label</Pill>);
    expect(screen.getByText('Label')).toHaveClass(`ui-pill-${variant}`);
  });

  it.each(['soft', 'outline'])('applies the %s tone', (tone) => {
    render(<Pill tone={tone}>Label</Pill>);
    expect(screen.getByText('Label')).toHaveClass(`ui-pill-${tone}`);
  });

  it('falls back to neutral and soft for unknown values', () => {
    render(
      <Pill variant="bogus" tone="bogus">
        Label
      </Pill>,
    );
    expect(screen.getByText('Label')).toHaveClass(
      'ui-pill-neutral',
      'ui-pill-soft',
    );
  });

  it.each([
    ['check', '✓'],
    ['x', '✕'],
    ['dot', '●'],
  ])('renders an aria-hidden %s glyph', (icon, glyph) => {
    render(<Pill icon={icon}>Label</Pill>);
    const el = screen.getByText(glyph);
    expect(el).toHaveAttribute('aria-hidden', 'true');
  });

  it('renders no glyph when icon is null or unknown', () => {
    const { container, rerender } = render(<Pill>Label</Pill>);
    expect(container.querySelector('.ui-pill-icon')).toBeNull();
    rerender(<Pill icon="star">Label</Pill>);
    expect(container.querySelector('.ui-pill-icon')).toBeNull();
  });

  it('merges a custom className', () => {
    render(<Pill className="extra">Label</Pill>);
    expect(screen.getByText('Label')).toHaveClass('ui-pill', 'extra');
  });
});
