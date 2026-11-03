import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import NavGroup from './NavGroup.jsx';

const ITEMS = [
  { id: 'eligibility', label: 'Eligibility', disabled: true, reason: 'Pick a client first' },
  { id: 'onezero', label: 'Monthly employment' },
  { id: 'rules', label: 'Programs' },
];

const setup = (props = {}) => {
  const onSelect = vi.fn();
  render(<NavGroup label="What is it worth" items={ITEMS} activeId={null} onSelect={onSelect} {...props} />);
  return { onSelect, trigger: screen.getByRole('button', { name: /What is it worth/ }) };
};

describe('NavGroup', () => {
  it('is a menu button that starts closed and keeps no menu in the DOM', () => {
    const { trigger } = setup();
    expect(trigger).toHaveAttribute('aria-haspopup', 'menu');
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('opens on click and lists every item as a menuitem', async () => {
    const { trigger } = setup();
    await userEvent.click(trigger);
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getAllByRole('menuitem')).toHaveLength(3);
  });

  it('opens on the first item with ArrowDown and the last with ArrowUp', async () => {
    const { trigger } = setup();
    trigger.focus();
    await userEvent.keyboard('{ArrowDown}');
    await waitFor(() => expect(screen.getByRole('menuitem', { name: /Eligibility/ })).toHaveFocus());
    await userEvent.keyboard('{Escape}');
    expect(trigger).toHaveFocus();
    await userEvent.keyboard('{ArrowUp}');
    await waitFor(() => expect(screen.getByRole('menuitem', { name: /Programs/ })).toHaveFocus());
  });

  it('opens with Enter and Space, which a button does natively', async () => {
    const { trigger } = setup();
    trigger.focus();
    await userEvent.keyboard('{Enter}');
    expect(screen.getByRole('menu')).toBeInTheDocument();
    await userEvent.keyboard('{Escape}');
    await userEvent.keyboard(' ');
    expect(screen.getByRole('menu')).toBeInTheDocument();
  });

  it('moves with arrows, wraps, and jumps with Home and End', async () => {
    const { trigger } = setup();
    trigger.focus();
    await userEvent.keyboard('{ArrowDown}');
    await waitFor(() => expect(screen.getAllByRole('menuitem')[0]).toHaveFocus());
    await userEvent.keyboard('{ArrowDown}');
    expect(screen.getAllByRole('menuitem')[1]).toHaveFocus();
    await userEvent.keyboard('{End}');
    expect(screen.getAllByRole('menuitem')[2]).toHaveFocus();
    await userEvent.keyboard('{ArrowDown}');
    expect(screen.getAllByRole('menuitem')[0]).toHaveFocus();
    await userEvent.keyboard('{ArrowUp}');
    expect(screen.getAllByRole('menuitem')[2]).toHaveFocus();
    await userEvent.keyboard('{Home}');
    expect(screen.getAllByRole('menuitem')[0]).toHaveFocus();
  });

  it('closes on Escape and returns focus to the trigger', async () => {
    const { trigger } = setup();
    await userEvent.click(trigger);
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('closes on Tab and on a click outside', async () => {
    const { trigger } = setup();
    await userEvent.click(trigger);
    screen.getAllByRole('menuitem')[1].focus();
    await userEvent.tab();
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();

    await userEvent.click(trigger);
    expect(screen.getByRole('menu')).toBeInTheDocument();
    await userEvent.click(document.body);
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('selects an enabled item and closes', async () => {
    const { trigger, onSelect } = setup();
    await userEvent.click(trigger);
    await userEvent.click(screen.getByRole('menuitem', { name: /Monthly employment/ }));
    expect(onSelect).toHaveBeenCalledWith('onezero');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('shows a disabled item WITH its reason, keeps it focusable, and never selects it', async () => {
    const { trigger, onSelect } = setup();
    await userEvent.click(trigger);
    const item = screen.getByRole('menuitem', { name: /Eligibility/ });
    expect(item).toHaveAttribute('aria-disabled', 'true');
    expect(item).not.toBeDisabled();
    expect(screen.getByText('Pick a client first')).toBeInTheDocument();
    await userEvent.click(item);
    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.getByRole('menu')).toBeInTheDocument();
  });

  it('marks the group and the item where you are', async () => {
    const { trigger } = setup({ activeId: 'rules' });
    expect(trigger).toHaveClass('is-active');
    await userEvent.click(trigger);
    expect(screen.getByRole('menuitem', { name: /Programs/ })).toHaveAttribute('aria-current', 'page');
  });
});
