import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { NAV } from '../../App.jsx';
import { groupOf, navGroups, NEEDS_CLIENT_REASON } from '../../lib/shellNav.js';
import AppShell from './AppShell.jsx';
import ShellActions from './ShellActions.jsx';
import TopBar from './TopBar.jsx';

const GROUPS = navGroups(NAV, { hasClient: true });

describe('navGroups', () => {
  it('turns every NAV section into a group and every item into an entry', () => {
    expect(GROUPS.map((g) => g.section)).toEqual(NAV.map((g) => g.section));
    const ids = GROUPS.flatMap((g) => g.items.map((i) => i.id));
    expect(ids).toEqual(NAV.flatMap((g) => g.items.map((i) => i.id)));
  });

  it('disables a client-bound entry WITH a reason when no client is picked', () => {
    const book = navGroups(NAV, { hasClient: false }).flatMap((g) => g.items);
    const eligibility = book.find((i) => i.id === 'eligibility');
    expect(eligibility).toMatchObject({ disabled: true, reason: NEEDS_CLIENT_REASON });
    expect(book.filter((i) => i.disabled).map((i) => i.id)).toEqual(['eligibility']);
  });

  it('enables everything once a client is picked', () => {
    expect(GROUPS.flatMap((g) => g.items).some((i) => i.disabled)).toBe(false);
  });

  it('knows which group an item belongs to', () => {
    expect(groupOf(NAV, 'evidence')).toBe('Prove it');
    expect(groupOf(NAV, 'nope')).toBeNull();
  });
});

describe('TopBar', () => {
  it('renders every NAV group under a Primary landmark', () => {
    render(<TopBar groups={GROUPS} activeId={null} onSelect={() => {}} onHome={() => {}} />);
    const nav = screen.getByRole('navigation', { name: 'Primary' });
    for (const group of NAV) {
      expect(within(nav).getByRole('button', { name: new RegExp(group.section) })).toBeInTheDocument();
    }
  });

  it('opens a group and reaches every item of it', async () => {
    const onSelect = vi.fn();
    render(<TopBar groups={GROUPS} activeId={null} onSelect={onSelect} onHome={() => {}} />);
    for (const group of NAV) {
      await userEvent.click(screen.getByRole('button', { name: new RegExp(group.section) }));
      const labels = screen.getAllByRole('menuitem').map((el) => el.textContent);
      for (const item of group.items) expect(labels.join('|')).toContain(item.label);
      await userEvent.keyboard('{Escape}');
    }
  });

  it('renders a one-item group as a direct link, not a one-choice menu', async () => {
    const onSelect = vi.fn();
    const single = [{ section: 'Solo', items: [{ id: 'rules', label: 'Programs' }] }];
    render(<TopBar groups={single} activeId={null} onSelect={onSelect} onHome={() => {}} />);
    await userEvent.click(screen.getByRole('button', { name: 'Programs' }));
    expect(onSelect).toHaveBeenCalledWith('rules');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('goes home from the brand', async () => {
    const onHome = vi.fn();
    render(<TopBar groups={GROUPS} activeId={null} onSelect={() => {}} onHome={onHome} />);
    await userEvent.click(screen.getByRole('button', { name: /the book/ }));
    expect(onHome).toHaveBeenCalled();
  });
});

describe('AppShell', () => {
  it('has a skip link that targets the one main landmark, and focus reaches it first', async () => {
    render(<AppShell header={<button type="button">bar</button>} mainLabel="Position" main={<p>page</p>} />);
    const skip = screen.getByRole('link', { name: 'Skip to content' });
    expect(skip).toHaveAttribute('href', '#main-content');
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main-content');
    expect(screen.getAllByRole('main')).toHaveLength(1);
    await userEvent.tab();
    expect(skip).toHaveFocus();
    await userEvent.tab();
    expect(screen.getByRole('button', { name: 'bar' })).toHaveFocus();
  });

  it('puts the header in a banner landmark and extras after main', () => {
    render(<AppShell header={<span>hdr</span>} mainLabel="Position" main={<p>page</p>}><i>extra</i></AppShell>);
    expect(within(screen.getByRole('banner')).getByText('hdr')).toBeInTheDocument();
    expect(screen.getByRole('main')).not.toContainElement(screen.getByText('extra'));
  });
});

describe('ShellActions', () => {
  const scopeProps = { page: 'portfolio', options: null, scope: {}, resolved: {}, onChange: () => {} };

  it('shows no account menu when nobody is signed in', () => {
    render(<MemoryRouter><ShellActions scopeProps={scopeProps} identity={{ authenticated: false }} /></MemoryRouter>);
    expect(screen.queryByRole('button', { name: /Account/ })).not.toBeInTheDocument();
  });

  it('shows initials and the UPN once signed in, and closes on Escape', async () => {
    render(<MemoryRouter>
      <ShellActions
        scopeProps={scopeProps}
        identity={{ authenticated: true, upn: 'jane.doe@example.com', auth_mode: 'entra' }}
      />
    </MemoryRouter>);
    const avatar = screen.getByRole('button', { name: /Account: jane.doe@example.com/ });
    await userEvent.click(avatar);
    expect(screen.getByRole('region', { name: 'Account' })).toBeInTheDocument();
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('region', { name: 'Account' })).not.toBeInTheDocument();
    expect(avatar).toHaveFocus();
  });
});
