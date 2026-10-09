/**
 * The book grid: sorting, the declining band, and the map as a filter.
 *
 * Three of the partner's §2 slices meet in this component, and each of them has a
 * failure mode that renders perfectly and says the wrong thing:
 *
 *  - A dollar sort silently discarding the band ranking, so the screen looks
 *    ordered by priority and is not.
 *  - A falling client reading as `settled` — "Nothing outstanding" — which is
 *    the reading this band exists to correct.
 *  - A map selecting through its own mechanism instead of the shared filter
 *    grammar, so the map and the chips disagree about what is on screen.
 *
 * None of those throws. All three are checked here.
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import BookGrid from './BookGrid.jsx';
import { DEFAULT_BOOK_SORT } from '../lib/bookSort.js';
import * as api from '../api.js';

vi.mock('../api.js', () => ({ fetchClientCoverage: vi.fn() }));

// The map pulls a 10MB topojson from a CDN on mount. The filtering behaviour
// under test is about what it CALLS, not about the geography, so it is stubbed
// down to the states the book actually holds.
vi.mock('./FootprintMap.jsx', () => ({
  default: ({ states, priced, selected, onSelect }) => (
    <div data-testid="map">
      {states.map((code) => (
        <button
          key={code}
          type="button"
          aria-pressed={selected.includes(code)}
          data-priced={priced.includes(code)}
          onClick={() => onSelect(code)}
        >
          {code}
        </button>
      ))}
    </div>
  ),
}));

const HALLOWAY = {
  client_id: 2004,
  client_name: 'Halloway',
  priority_band: 'declining',
  priority_rank: 2,
  program_code: 'GA_JTC',
  tax_year: 2025,
  identified_usd: '0',
  opportunity_usd: '0',
  jobs_margin: -2,
  states: ['GA', 'SC'],
  priceable_states: ['GA', 'SC'],
  trend: {
    declining: true,
    years_falling: 3,
    peak_tax_year: 2022,
    fallen_by: 39.33,
    below_base: true,
    credit_earned_usd: '208845',
  },
};

const CASCADE = {
  client_id: 2001,
  client_name: 'Cascade',
  industry: 'Retail',
  priority_band: 'unclaimed_at_scale',
  priority_rank: 3,
  program_code: 'GA_JTC',
  tax_year: 2025,
  identified_usd: '72660',
  opportunity_usd: '72660',
  jobs_margin: 40,
  states: ['GA', 'NC', 'SC'],
  priceable_states: ['GA', 'SC'],
};

function draw(overrides = {}) {
  const onFilter = vi.fn();
  const onSort = vi.fn();
  render(
    <BookGrid
      rows={[HALLOWAY, CASCADE]}
      year={2025}
      filters={{}}
      onFilter={onFilter}
      sort={{ ...DEFAULT_BOOK_SORT }}
      onSort={onSort}
      unassessedCount={0}
      {...overrides}
    />,
  );
  return { onFilter, onSort };
}

describe('sorting the book', () => {
  it('asks the page to sort rather than reordering what it was given', async () => {
    // Server-side. The endpoint holds the whole book; re-sorting one page in
    // the browser would disagree with the total the moment it outgrows a page.
    const { onSort } = draw();
    await userEvent.click(screen.getByRole('button', { name: /Identified/ }));
    expect(onSort).toHaveBeenCalledWith('identified', expect.anything());
  });

  it('says on screen that a value sort has set the ranking aside', async () => {
    draw({ sort: { key: 'identified', desc: true } });
    expect(screen.getByText(/Ranked by value, not by targeting/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Return to targeting order/ })).toBeInTheDocument();
  });

  it('makes no such claim while the band ranking is in force', () => {
    draw();
    expect(screen.queryByText(/Ranked by value, not by targeting/)).not.toBeInTheDocument();
    expect(screen.getByText(/Ranked by targeting/)).toBeInTheDocument();
  });

  it('marks the active column for a screen reader, not only with an arrow', () => {
    draw({ sort: { key: 'identified', desc: true } });
    const header = screen.getByRole('columnheader', { name: /Identified/ });
    expect(header).toHaveAttribute('aria-sort', 'descending');
  });

  it('offers no sort on a column the endpoint cannot order by', () => {
    // `_portfolio_sort_key` has no alias for programme. A header that looks
    // sortable and does nothing is worse than a plain one. The filter toggle
    // is still there, so this asks for the SORT control specifically.
    draw();
    const header = screen.getByRole('columnheader', { name: /Program/ });
    expect(header.querySelector('.th-sort')).toBeNull();
    expect(header).not.toHaveAttribute('aria-sort');
  });
});

describe('the declining band', () => {
  it('names the size of the fall, and what it puts at risk', () => {
    draw();
    const row = screen.getByRole('row', { name: /Halloway/ });
    expect(within(row).getByText(/↓ 39.3 jobs since TY2022/)).toBeInTheDocument();
    // The credit ALREADY EARNED is what is at risk. This year's `identified`
    // is $0 and would read as an opportunity.
    expect(within(row).getByText(/\$209k earned/)).toBeInTheDocument();
  });

  it('does not render a forecast in the same grammar as a finding', () => {
    // `exposed` is a finding against a filed return; this is a projection.
    // Same urgency, and it must not look like the same kind of statement.
    draw();
    const chip = screen.getByText('Declining');
    expect(chip.className).toContain('tcc-band-forecast');
    expect(chip.className).not.toContain('tcc-band-bad');
  });

  it('says nothing about a client that is not falling', () => {
    draw();
    const row = screen.getByRole('row', { name: /Cascade/ });
    expect(within(row).queryByText(/jobs since TY/)).toBeNull();
  });
});

describe('the map filters the book', () => {
  it('writes the shared state filter rather than holding its own selection', async () => {
    // If the map kept its own selection, clearing the chip in the filter bar
    // would leave the map still looking selected.
    const { onFilter } = draw();
    await userEvent.click(within(screen.getByTestId('map')).getByRole('button', { name: 'NC' }));
    expect(onFilter).toHaveBeenCalledWith({ state: 'NC' });
  });

  it('toggles a state off when it is already selected', async () => {
    const { onFilter } = draw({ filters: { state: 'NC' } });
    await userEvent.click(within(screen.getByTestId('map')).getByRole('button', { name: 'NC' }));
    expect(onFilter).toHaveBeenCalledWith({ state: '' });
  });

  it('keeps held-but-unpriceable states visually distinct', () => {
    // Cascade has payroll in NC and there is no authored NC pack. That is a
    // real gap in statutory coverage and must not look like a priced state.
    draw();
    const map = within(screen.getByTestId('map'));
    expect(map.getByRole('button', { name: 'GA' })).toHaveAttribute('data-priced', 'true');
    expect(map.getByRole('button', { name: 'NC' })).toHaveAttribute('data-priced', 'false');
  });

  it('offers every state anyone in the book operates in', () => {
    // The union, not one client's footprint — the map filters the whole book.
    // SC belongs to both, NC only to Cascade, and all three must be clickable.
    draw();
    const map = within(screen.getByTestId('map'));
    expect(map.getByRole('button', { name: 'GA' })).toBeInTheDocument();
    expect(map.getByRole('button', { name: 'NC' })).toBeInTheDocument();
    expect(map.getByRole('button', { name: 'SC' })).toBeInTheDocument();
  });
});

describe('expanding a row', () => {
  // The drill-down outlived the parent's cleanup: it kept a Claimed column and
  // an Outcome column reading `over claimed` / `unclaimed` / `correctly not
  // claimed`, every one of which asserts something about a filing we do not
  // hold. Nothing tested these columns, which is why they survived.

  const CELLS = {
    cells: [
      {
        program_code: 'GA_JTC', tax_year: 2020, priority_band: 'settled',
        identified_usd: '0', claimed_usd: null, jobs_margin: -2, is_base_year: true,
        outcome: 'base_year',
      },
      {
        program_code: 'GA_JTC', tax_year: 2022, priority_band: 'unclaimed_at_scale',
        identified_usd: '31185', claimed_usd: '95000', jobs_margin: 8.91,
        is_base_year: false, provenance_verified: false, outcome: 'over_claimed',
      },
    ],
  };

  async function expandCascade() {
    api.fetchClientCoverage.mockResolvedValue(CELLS);
    draw();
    await userEvent.click(screen.getByRole('button', { name: /Expand Cascade/ }));
    await screen.findByText('$31k');
    return within(document.querySelector('.tcc-expand-table'));
  }

  it('shows no claimed figure and no claim-derived outcome', async () => {
    const table = await expandCascade();
    expect(table.queryByRole('columnheader', { name: 'Claimed' })).toBeNull();
    expect(table.queryByRole('columnheader', { name: 'Outcome' })).toBeNull();
    expect(table.queryByText('$95k')).toBeNull();
    expect(table.queryByText(/over claimed/)).toBeNull();
  });

  it('keeps the figures it computed', async () => {
    const table = await expandCascade();
    expect(table.getByText('$31k')).toBeInTheDocument();
    expect(table.getByText('8.91 over')).toBeInTheDocument();
  });

  it('still says which year is the base year', async () => {
    // The one thing Outcome carried that was not about a filing, and it is why
    // `identified` is $0 on that row.
    const table = await expandCascade();
    const row = table.getByRole('row', { name: /TY2020/ });
    expect(within(row).getByText('base year')).toBeInTheDocument();
  });
});

describe('the state list beside the map', () => {
  // The map alone was two thirds whitespace: we hold four states and the other
  // forty-six were the picture. The list fills it with the thing the map is a
  // control for, and gives the same filter a keyboard can reach.

  function stateRow(code) {
    return screen.getByRole('row', { name: new RegExp(`^${code}\\b`) });
  }

  it('counts clients per state', () => {
    draw();
    // GA: both. NC: Cascade only. SC: both.
    expect(within(stateRow('GA')).getAllByRole('cell')[1]).toHaveTextContent('2');
    expect(within(stateRow('NC')).getAllByRole('cell')[1]).toHaveTextContent('1');
  });

  it('shows no per-state dollar figure', () => {
    // A claim is client-grain and a client operates in several states, so any
    // per-state money total would either double-count or credit a state that
    // did not earn it.
    draw();
    expect(stateRow('GA').textContent).not.toMatch(/\$/);
    expect(stateRow('NC').textContent).not.toMatch(/\$/);
  });

  it('names the coverage gap in words, not only as a shade', () => {
    draw();
    expect(stateRow('GA')).toHaveTextContent('Priced');
    expect(stateRow('NC')).toHaveTextContent('No authored statute');
  });

  it('writes the same filter the map does', () => {
    const { onFilter } = draw();
    return userEvent
      .click(within(stateRow('NC')).getByRole('button', { name: 'NC' }))
      .then(() => expect(onFilter).toHaveBeenCalledWith({ state: 'NC' }));
  });
});


describe('industry on the book (WI-20)', () => {
  it('shows each client\u2019s industry, and says so where none is recorded', () => {
    draw();
    expect(screen.getByRole('columnheader', { name: /Industry/ })).toBeInTheDocument();
    const cascade = screen.getByRole('button', { name: 'Open Cascade' }).closest('tr');
    expect(cascade).toHaveTextContent('Retail');
    const halloway = screen.getByRole('button', { name: /Open Halloway/ }).closest('tr');
    expect(halloway).toHaveTextContent('Not recorded');
  });
});
