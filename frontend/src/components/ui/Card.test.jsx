import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import Card from './Card';

describe('Card', () => {
  it('renders children in a section with no header when nothing is given', () => {
    const { container } = render(<Card>Body</Card>);
    expect(screen.getByText('Body')).toBeInTheDocument();
    expect(container.querySelector('section')).toHaveClass(
      'ui-card',
      'ui-card-neutral',
    );
    expect(container.querySelector('header')).toBeNull();
    expect(container.querySelector('section')).not.toHaveAttribute(
      'aria-labelledby',
    );
  });

  it('labels the section by its title', () => {
    render(<Card title="Position">Body</Card>);
    const region = screen.getByRole('region', { name: 'Position' });
    const heading = screen.getByRole('heading', { name: 'Position' });
    expect(region).toHaveAttribute('aria-labelledby', heading.id);
  });

  it('gives each card its own title id', () => {
    render(
      <>
        <Card title="One">a</Card>
        <Card title="Two">b</Card>
      </>,
    );
    const ids = screen.getAllByRole('heading').map((h) => h.id);
    expect(new Set(ids).size).toBe(2);
  });

  it('renders subtitle and actions in the header', () => {
    render(
      <Card title="T" subtitle="Sub" actions={<button>Export</button>}>
        Body
      </Card>,
    );
    expect(screen.getByText('Sub')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Export' })).toBeInTheDocument();
  });

  it('renders a header for actions alone, without a label', () => {
    const { container } = render(
      <Card actions={<button>Go</button>}>Body</Card>,
    );
    expect(container.querySelector('header')).not.toBeNull();
    expect(container.querySelector('h3')).toBeNull();
    expect(container.querySelector('section')).not.toHaveAttribute(
      'aria-labelledby',
    );
  });

  it('renders the tabs slot and footer', () => {
    const { container } = render(
      <Card title="T" tabs={<div>Tabs here</div>} footer={<span>Foot</span>}>
        Body
      </Card>,
    );
    const tabs = container.querySelector('.ui-card-tabs');
    expect(within(tabs).getByText('Tabs here')).toBeInTheDocument();
    expect(container.querySelector('footer')).toHaveTextContent('Foot');
  });

  it('applies the subtle tone', () => {
    const { container } = render(<Card tone="subtle">Body</Card>);
    expect(container.firstChild).toHaveClass('ui-card-subtle');
  });

  it('renders as another element', () => {
    const { container } = render(
      <Card as="article" title="T">
        Body
      </Card>,
    );
    expect(container.querySelector('article')).toHaveClass('ui-card');
    expect(container.querySelector('section')).toBeNull();
  });

  it('merges a custom className', () => {
    const { container } = render(<Card className="extra">Body</Card>);
    expect(container.firstChild).toHaveClass('ui-card', 'extra');
  });
});
