import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import Stepper from './Stepper.jsx';

const steps = [
  { id: 'a', label: 'Connect', status: 'done', href: '/a' },
  { id: 'b', label: 'Review', status: 'current' },
  { id: 'c', label: 'Claim', status: 'upcoming' },
  { id: 'd', label: 'File', status: 'disabled' },
];

describe('Stepper', () => {
  it('renders a labelled nav with one list item per step', () => {
    render(<Stepper steps={steps} onSelect={() => {}} />);
    expect(screen.getByRole('navigation', { name: 'Progress' })).toBeInTheDocument();
    expect(screen.getAllByRole('listitem')).toHaveLength(4);
  });

  it('accepts a custom nav label', () => {
    render(<Stepper steps={steps} label="Claim steps" />);
    expect(screen.getByRole('navigation', { name: 'Claim steps' })).toBeInTheDocument();
  });

  it('marks only the current step with aria-current', () => {
    const { container } = render(<Stepper steps={steps} onSelect={() => {}} />);
    const current = container.querySelectorAll('[aria-current="step"]');
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveTextContent('Review');
  });

  it('renders each status with its class and a done glyph', () => {
    const { container } = render(<Stepper steps={steps} />);
    ['done', 'current', 'upcoming', 'disabled'].forEach((s) => {
      expect(container.querySelector(`.ui-stepper__item--${s}`)).toBeInTheDocument();
    });
    expect(container.querySelector('.ui-stepper__item--done .ui-stepper__marker')).toHaveTextContent('✓');
    expect(screen.getByText('(completed)')).toBeInTheDocument();
  });

  it('renders an anchor for a step with href', () => {
    render(<Stepper steps={steps} />);
    expect(screen.getByRole('link', { name: /Connect/ })).toHaveAttribute('href', '/a');
  });

  it('renders buttons for onSelect steps and calls onSelect with the id', async () => {
    const onSelect = vi.fn();
    render(<Stepper steps={steps} onSelect={onSelect} />);
    await userEvent.click(screen.getByRole('button', { name: /Claim/ }));
    expect(onSelect).toHaveBeenCalledWith('c');
  });

  it('operates by keyboard', async () => {
    const onSelect = vi.fn();
    render(<Stepper steps={steps} onSelect={onSelect} />);
    const button = screen.getByRole('button', { name: /Claim/ });
    button.focus();
    await userEvent.keyboard('{Enter}');
    await userEvent.keyboard(' ');
    expect(onSelect).toHaveBeenCalledTimes(2);
  });

  it('prefers a step-level onSelect', async () => {
    const own = vi.fn();
    const shared = vi.fn();
    render(
      <Stepper
        steps={[{ id: 'x', label: 'Own', status: 'upcoming', onSelect: own }]}
        onSelect={shared}
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: /Own/ }));
    expect(own).toHaveBeenCalledWith('x');
    expect(shared).not.toHaveBeenCalled();
  });

  it('keeps disabled steps out of the tab order and inert', async () => {
    const onSelect = vi.fn();
    render(
      <Stepper
        steps={[{ id: 'd', label: 'Locked', status: 'disabled', href: '/d', onSelect }]}
      />,
    );
    const el = screen.getByText('Locked').closest('.ui-stepper__control');
    expect(el.tagName).toBe('SPAN');
    expect(el).toHaveAttribute('aria-disabled', 'true');
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.queryByRole('link')).toBeNull();
    await userEvent.click(el);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('renders a plain span for a step with no href and no handler', () => {
    render(<Stepper steps={[{ id: 'p', label: 'Plain', status: 'upcoming' }]} />);
    const el = screen.getByText('Plain').closest('.ui-stepper__control');
    expect(el.tagName).toBe('SPAN');
    expect(el).not.toHaveAttribute('aria-disabled');
  });

  it('renders an empty list without steps', () => {
    render(<Stepper />);
    expect(screen.queryAllByRole('listitem')).toHaveLength(0);
  });
});
