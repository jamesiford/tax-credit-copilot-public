import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import HeroBand from './HeroBand.jsx';

describe('HeroBand', () => {
  it('renders a header with an h1 by default', () => {
    const { container } = render(<HeroBand title="Welcome back" />);
    expect(container.querySelector('header')).toHaveClass('ui-hero');
    expect(screen.getByRole('heading', { level: 1, name: 'Welcome back' })).toBeInTheDocument();
  });

  it('renders the requested heading level', () => {
    render(<HeroBand title="Section" level={2} />);
    expect(screen.getByRole('heading', { level: 2, name: 'Section' })).toBeInTheDocument();
  });

  it('clamps an invalid level into h1..h6', () => {
    const { rerender } = render(<HeroBand title="T" level={9} />);
    expect(screen.getByRole('heading', { level: 6 })).toBeInTheDocument();
    rerender(<HeroBand title="T" level="abc" />);
    expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument();
  });

  it('renders the subline and aside slots only when given', () => {
    const { container, rerender } = render(<HeroBand title="T" />);
    expect(container.querySelector('.ui-hero__sub')).toBeNull();
    expect(container.querySelector('.ui-hero__aside')).toBeNull();
    rerender(
      <HeroBand title="T" aside={<button type="button">Act</button>}>
        Two things need you
      </HeroBand>,
    );
    expect(screen.getByText('Two things need you')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Act' })).toBeInTheDocument();
  });

  it('applies the compact variant', () => {
    const { container, rerender } = render(<HeroBand title="T" />);
    expect(container.querySelector('header')).not.toHaveClass('ui-hero--compact');
    rerender(<HeroBand title="T" compact />);
    expect(container.querySelector('header')).toHaveClass('ui-hero--compact');
  });
});
