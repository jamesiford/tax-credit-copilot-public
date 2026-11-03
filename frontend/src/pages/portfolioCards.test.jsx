/**
 * The book as a dashboard: cards in a decided order, tabs that carry counts,
 * tiles tinted by a reading, and a map that is a filter.
 *
 * Each of these renders fine when it is wrong. A tab count taken from the
 * filtered rows, a tile coloured by topic, or a tab that filters through its
 * own mechanism all look plausible and say the wrong thing.
 */
import { render as rawRender, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import PortfolioPage from './PortfolioPage.jsx';

vi.mock('../api.js', async () => {
  const actual = await vi.importActual('../api.js');
  return {
    ...actual,
    fetchPortfolioV2: vi.fn(),
    fetchClientCoverage: vi.fn().mockResolvedValue({ cells: [], totals: {} }),
  };
});

// The map pulls its geography from a CDN; the card around it is what is tested.
vi.mock('../components/FootprintMap.jsx', () => ({
  default: ({ states }) => <div data-testid="map">{states.join(',')}</div>,
}));

const api = await import('../api.js');

const ROWS = [
  {
    client_id: 2001, client_name: 'Cascade', program_code: 'GA_JTC', tax_year: 2023,
    priority_band: 'exposed', priority_rank: 0, jobs_margin: 3, identified_usd: '31000',
    states: ['GA', 'NC'], priceable_states: ['GA'],
  },
  {
    client_id: 2002, client_name: 'Northwind', program_code: 'GA_JTC', tax_year: 2023,
    priority_band: 'unclaimed_at_scale', priority_rank: 3, jobs_margin: 48, identified_usd: '607110',
    states: ['GA'], priceable_states: ['GA'],
  },
  {
    client_id: 2003, client_name: 'Lakeshore', program_code: 'GA_JTC', tax_year: 2023,
    priority_band: 'unclaimed_at_scale', priority_rank: 3, jobs_margin: 20, identified_usd: '90000',
    states: ['GA'], priceable_states: ['GA'],
  },
];

function Where() {
  const loc = useLocation();
  return <div data-testid="where">{loc.search}</div>;
}

function draw(initial = '/') {
  api.fetchPortfolioV2.mockResolvedValue({
    total_clients: 3, assessed_clients: 3, unassessed_clients: 0, items: ROWS,
  });
  return rawRender(
    <MemoryRouter initialEntries={[initial]}>
      <PortfolioPage scopeOptions={{ clients: [], programs: [] }} scope={{ clientId: 'portfolio' }} />
      <Where />
    </MemoryRouter>,
  );
}

afterEach(() => vi.clearAllMocks());

describe('the portfolio dashboard', () => {
  it('puts the book first and the footprint and position cards beneath it', async () => {
    draw();
    await screen.findByRole('button', { name: 'Open Cascade' });
    const titles = [...document.querySelectorAll('.ui-card-title')].map((n) => n.textContent);
    expect(titles).toEqual(['The book', 'Where the book operates', 'Position']);
  });

  it('keeps the book as the full-width card and the others in the card grid', async () => {
    draw();
    await screen.findByRole('button', { name: 'Open Cascade' });
    const grid = document.querySelector('.tcc-card-grid');
    expect(grid.querySelectorAll(':scope > .ui-card')).toHaveLength(2);
    expect(grid.querySelector('.tcc-book-card')).toBeNull();
  });

  it('opens on the complete population and every tab carries its count', async () => {
    draw();
    await screen.findByRole('button', { name: 'Open Cascade' });
    const tabs = within(screen.getByRole('tablist', { name: 'Population' })).getAllByRole('tab');
    expect(tabs.map((t) => t.textContent)).toEqual([
      'All clients3', 'Exposed1', 'Identified2',
    ]);
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true');
  });

  it('a tab writes the same band filter the column header writes', async () => {
    draw();
    await screen.findByRole('button', { name: 'Open Cascade' });
    await userEvent.click(screen.getByRole('tab', { name: /Identified/ }));
    expect(screen.getByTestId('where')).toHaveTextContent('bf=band%3Aunclaimed_at_scale');
    // The list narrows; the counts on the tabs do not.
    expect(screen.queryByRole('button', { name: 'Open Cascade' })).toBeNull();
    expect(screen.getByRole('tab', { name: /All clients/ })).toHaveTextContent('3');
  });

  it('tints a position tile by the reading it means, through a state class', async () => {
    draw();
    await screen.findByRole('button', { name: 'Open Cascade' });
    const group = screen.getByRole('group', { name: 'Clients by targeting band' });
    const tiles = [...group.querySelectorAll('.ui-kpi')];
    expect(tiles.map((t) => t.className.match(/ui-kpi-([a-z-]+)/)[1])).toEqual(['below-min', 'above-min']);
    expect(within(group).getByText('Exposed').closest('.ui-kpi')).toHaveTextContent('1');
  });

  it('shows no dollar total: money is the warehouse\u2019s to sum', async () => {
    draw();
    await screen.findByRole('button', { name: 'Open Cascade' });
    const position = screen.getByRole('region', { name: 'Position' });
    expect(position.textContent).not.toMatch(/\$/);
  });

  it('the map card says which state the book is filtered to', async () => {
    draw('/?bf=state%3ANC');
    await screen.findByText('Filtered to NC');
    await waitFor(() => expect(screen.getByTestId('map')).toHaveTextContent('GA,NC'));
  });
});
