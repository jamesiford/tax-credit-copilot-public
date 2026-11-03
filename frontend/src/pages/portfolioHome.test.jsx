import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { START_HERE_KEY } from '../lib/startHere.js';
import PortfolioPage from './PortfolioPage.jsx';

vi.mock('../api.js', async () => {
  const actual = await vi.importActual('../api.js');
  return { ...actual, fetchPortfolioV2: vi.fn() };
});

const api = await import('../api.js');

const ROWS = [
  {
    client_id: 2001, client_name: 'Cascade', program_code: 'GA_JTC', tax_year: 2023,
    priority_band: 'on_the_line', priority_rank: 1, jobs_margin: -0.4, gap_jobs: 0.4,
    identified_usd: '0', claimed_usd: '0', opportunity_usd: '0', is_exposure: false,
  },
  {
    client_id: 2002, client_name: 'Northwind', program_code: 'GA_JTC', tax_year: 2023,
    priority_band: 'unclaimed_at_scale', priority_rank: 2, jobs_margin: 48.0, gap_jobs: 0,
    identified_usd: '607110', claimed_usd: '0', opportunity_usd: '607110', is_exposure: false,
  },
];

function Where() {
  const location = useLocation();
  return <span data-testid="where">{location.pathname + location.search}</span>;
}

const draw = (props = {}, items = ROWS) => {
  api.fetchPortfolioV2.mockResolvedValue({
    total_clients: items.length, assessed_clients: items.length, unassessed_clients: 0, items,
  });
  return render(
    <MemoryRouter><PortfolioPage scopeOptions={null} {...props} /><Where /></MemoryRouter>,
  );
};

beforeEach(() => window.localStorage.clear());
afterEach(() => { vi.clearAllMocks(); window.localStorage.clear(); });

describe('the home page opens with a hero, the task cards, then the book', () => {
  it('has one h1 (the hero) and Targeting as the book\u2019s h2', async () => {
    draw();
    await screen.findByRole('button', { name: 'Open Cascade' });
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Welcome back');
    expect(screen.getByRole('heading', { level: 2, name: 'Targeting' })).toBeInTheDocument();
  });

  it('greets by first name when somebody is signed in', async () => {
    draw({ identity: { authenticated: true, upn: 'jane.doe@example.com' } });
    expect(await screen.findByRole('heading', { level: 1, name: 'Hi, Jane' })).toBeInTheDocument();
  });

  it('orders hero, then cards, then the grid', async () => {
    draw();
    const grid = await screen.findByRole('button', { name: 'Open Cascade' });
    const hero = screen.getByRole('heading', { level: 1 });
    const cards = screen.getByRole('region', { name: 'Start here' });
    const before = (a, b) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    expect(before(hero, cards)).toBe(true);
    expect(before(cards, grid)).toBe(true);
  });

  it('offers the four tasks as real links', async () => {
    draw();
    await screen.findByRole('button', { name: 'Open Cascade' });
    const cards = within(screen.getByRole('region', { name: 'Start here' }));
    expect(cards.getAllByRole('link')).toHaveLength(4);
    expect(cards.getByRole('link', { name: /Review a client/ })).toHaveAttribute('href', '/c/2001');
    expect(cards.getByRole('link', { name: /What if we hire/ })).toHaveAttribute('href', '/c/2001?ctab=whatif');
    expect(cards.getByRole('link', { name: /Prove the work/ })).toHaveAttribute('href', '/evidence');
  });

  it('routes each card in the app on a plain click', async () => {
    draw();
    await screen.findByRole('button', { name: 'Open Cascade' });
    await userEvent.click(screen.getByRole('link', { name: /What if we hire/ }));
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/c/2001?ctab=whatif'));
  });

  it('sends Prove the work to the audit trail', async () => {
    draw();
    await screen.findByRole('button', { name: 'Open Cascade' });
    await userEvent.click(screen.getByRole('link', { name: /Prove the work/ }));
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/evidence'));
  });

  it('falls back to the book, never a client that is not there, when the book is empty', async () => {
    draw({}, []);
    await waitFor(() => expect(api.fetchPortfolioV2).toHaveBeenCalled());
    const review = await screen.findByRole('link', { name: /Review a client/ });
    expect(review).toHaveAttribute('href', '#targeting');
    expect(screen.getByRole('link', { name: /What if we hire/ })).toHaveAttribute('href', '#targeting');
  });

  it('Who to call moves focus to the book heading', async () => {
    draw();
    await screen.findByRole('button', { name: 'Open Cascade' });
    await userEvent.click(screen.getByRole('link', { name: /Who to call/ }));
    expect(document.getElementById('targeting')).toHaveFocus();
  });
});

describe('Start here collapses, and the choice sticks', () => {
  it('is open on a first visit', async () => {
    draw();
    await screen.findByRole('button', { name: 'Open Cascade' });
    expect(screen.getByRole('button', { name: 'Start here' })).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('region', { name: 'Start here' })).toBeInTheDocument();
  });

  it('collapses on click, removes the cards, and remembers it', async () => {
    draw();
    await screen.findByRole('button', { name: 'Open Cascade' });
    await userEvent.click(screen.getByRole('button', { name: 'Start here' }));
    expect(screen.getByRole('button', { name: 'Start here' })).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('region', { name: 'Start here' })).not.toBeInTheDocument();
    expect(window.localStorage.getItem(START_HERE_KEY)).toBe('collapsed');
  });

  it('stays collapsed on the next visit, and reopens', async () => {
    window.localStorage.setItem(START_HERE_KEY, 'collapsed');
    draw();
    await screen.findByRole('button', { name: 'Open Cascade' });
    expect(screen.queryByRole('region', { name: 'Start here' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Start here' }));
    expect(screen.getByRole('region', { name: 'Start here' })).toBeInTheDocument();
    expect(window.localStorage.getItem(START_HERE_KEY)).toBe('expanded');
  });
});
