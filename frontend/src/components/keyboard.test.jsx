/**
 * Keyboard walkthroughs: the controls a pointer-free reader meets in order.
 *
 * Each of these is a control with its own widget semantics, so each is driven
 * with the keys it promises and nothing else. (Nav groups are walked in
 * shell/NavGroup.test.jsx, tabs in ui/Tabs.test.jsx, and the Ask workspace in
 * ask/AskWorkspace.ui.test.jsx.) A control that works by mouse and not by key is
 * a control that does not exist for somebody.
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import ClientHeader from './ClientHeader.jsx';
import { FilterBar } from './ColumnFilter.jsx';
import SortHeader from './SortHeader.jsx';
import { NUMERIC, TEXT } from '../lib/gridFilter.js';

function Where() {
  const loc = useLocation();
  return <div data-testid="where">{`${loc.pathname}${loc.search}`}</div>;
}

describe('the review stepper by keyboard', () => {
  it('Tab walks the steps in order, skips an unavailable one, and Enter follows a link', async () => {
    render(
      <MemoryRouter>
        <ClientHeader clientId={2001} clientName="Cascade" current="location" year={2023} onBack={() => {}} />
        <Where />
      </MemoryRouter>,
    );
    const flow = screen.getByRole('navigation', { name: 'Client review' });
    const links = within(flow).getAllByRole('link');
    expect(links).toHaveLength(6);

    screen.getByRole('button', { name: /Portfolio/ }).focus();
    const visited = [];
    for (let i = 0; i < links.length; i += 1) {
      await userEvent.tab();
      visited.push(document.activeElement.textContent.replace(/^\d+/, ''));
    }
    expect(visited).toEqual(['Position', 'Eligibility', 'Trend', 'At risk', 'What-if', 'Evidence']);

    await userEvent.keyboard('{Enter}');
    expect(screen.getByTestId('where')).toHaveTextContent('/c/2001/evidence?year=2023');
  });

  it('an unavailable step cannot take focus, so Tab goes straight past it', async () => {
    render(
      <MemoryRouter>
        <ClientHeader clientId={9} clientName="No payroll" onBack={() => {}} clientScope={{ payroll_years: [], calculable_years: [] }} />
      </MemoryRouter>,
    );
    screen.getByRole('button', { name: /Portfolio/ }).focus();
    await userEvent.tab();
    // The first thing after the way back is Evidence: the five that need a year
    // are not in the tab order.
    expect(document.activeElement).toHaveTextContent('Evidence');
  });
});

describe('a sortable, filterable header by keyboard', () => {
  const spec = { key: 'identified', label: 'Identified', type: NUMERIC };

  function Grid({ onSort = () => {}, onFilter = () => {} }) {
    return (
      <table>
        <thead>
          <tr>
            <SortHeader
              label="Identified"
              sortKey="identified"
              sort={[]}
              onSort={onSort}
              spec={spec}
              filters={{}}
              options={[]}
              onFilter={onFilter}
            />
          </tr>
        </thead>
      </table>
    );
  }

  it('Enter and Space both sort', async () => {
    const onSort = vi.fn();
    render(<Grid onSort={onSort} />);
    screen.getByRole('button', { name: 'Identified' }).focus();
    await userEvent.keyboard('{Enter}');
    await userEvent.keyboard(' ');
    expect(onSort).toHaveBeenCalledTimes(2);
    expect(onSort).toHaveBeenCalledWith('identified', expect.anything());
  });

  it('Tab reaches the filter toggle after the sort button, and Enter opens it', async () => {
    render(<Grid />);
    screen.getByRole('button', { name: 'Identified' }).focus();
    await userEvent.tab();
    const toggle = screen.getByRole('button', { name: 'Filter Identified' });
    expect(toggle).toHaveFocus();
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await userEvent.keyboard('{Enter}');
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
  });

  it('a chip in the filter bar is a button, and Clear all is reachable', async () => {
    const onClear = vi.fn();
    render(
      <FilterBar
        specs={{ client: { key: 'client', label: 'Client', type: TEXT } }}
        filters={{ client: '~cas' }}
        shown={1}
        total={5}
        noun="clients"
        onClear={onClear}
      />,
    );
    screen.getByRole('button', { name: /Clear all/ }).focus();
    await userEvent.keyboard('{Enter}');
    expect(onClear).toHaveBeenCalledWith(null);
    expect(screen.getByRole('status')).toHaveTextContent(/1 of 5/);
  });
});
