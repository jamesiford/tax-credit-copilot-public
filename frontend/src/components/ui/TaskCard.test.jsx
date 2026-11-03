import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import TaskCard from './TaskCard.jsx';

const props = {
  href: '/tasks/1',
  title: 'Review findings',
  description: 'Resolve the open findings before filing',
  category: 'Audit',
};

describe('TaskCard', () => {
  it('renders one link carrying the href', () => {
    render(<TaskCard {...props} />);
    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute('href', '/tasks/1');
  });

  it('names the link from the title and describes it with the description', () => {
    render(<TaskCard {...props} />);
    const link = screen.getByRole('link', { name: 'Review findings' });
    expect(link).toHaveAccessibleDescription('Resolve the open findings before filing');
  });

  it('keeps the full description in the title attribute', () => {
    render(<TaskCard {...props} />);
    expect(screen.getByText(props.description)).toHaveAttribute('title', props.description);
  });

  it('renders the category chip and hides decoration from assistive tech', () => {
    const { container } = render(<TaskCard {...props} icon={<span>★</span>} />);
    expect(container.querySelector('.ui-task-category')).toHaveTextContent('Audit');
    expect(container.querySelector('.ui-task-icon')).toHaveAttribute('aria-hidden', 'true');
    expect(container.querySelector('.ui-task-chevron')).toHaveAttribute('aria-hidden', 'true');
  });

  it('omits optional parts when absent', () => {
    const { container } = render(<TaskCard href="/x" title="Only title" />);
    expect(container.querySelector('.ui-task-category')).toBeNull();
    expect(container.querySelector('.ui-task-icon')).toBeNull();
    expect(container.querySelector('.ui-task-description')).toBeNull();
    expect(screen.getByRole('link')).not.toHaveAttribute('aria-describedby');
  });

  it('prevents default on a plain click and calls onClick', async () => {
    const onClick = vi.fn((e) => e.defaultPrevented);
    render(<TaskCard {...props} onClick={onClick} />);
    await userEvent.click(screen.getByRole('link'));
    expect(onClick).toHaveBeenCalledTimes(1);
    expect(onClick.mock.results[0].value).toBe(true);
  });

  it.each([
    ['ctrl', '{Control>}'],
    ['meta', '{Meta>}'],
    ['shift', '{Shift>}'],
    ['alt', '{Alt>}'],
  ])('leaves a %s-click to the browser', async (_name, key) => {
    const onClick = vi.fn();
    render(<TaskCard {...props} onClick={onClick} />);
    // Stop jsdom navigating so the click does not log a not-implemented error.
    const link = screen.getByRole('link');
    link.addEventListener('click', (e) => e.preventDefault());
    const user = userEvent.setup();
    await user.keyboard(key);
    await user.click(link);
    expect(onClick).not.toHaveBeenCalled();
  });

  it('ignores non-primary buttons', async () => {
    const onClick = vi.fn();
    render(<TaskCard {...props} onClick={onClick} />);
    const link = screen.getByRole('link');
    link.addEventListener('click', (e) => e.preventDefault());
    link.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, button: 1 }));
    expect(onClick).not.toHaveBeenCalled();
  });

  it('is operable by keyboard', async () => {
    const onClick = vi.fn();
    render(<TaskCard {...props} onClick={onClick} />);
    await userEvent.tab();
    expect(screen.getByRole('link')).toHaveFocus();
    await userEvent.keyboard('{Enter}');
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
