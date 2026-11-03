/**
 * The footprint panel: the map as a filter, and the list beside it.
 *
 * Moved out of BookGrid's tests with the component (UI-04): the book's grid and
 * its footprint are separate cards now. The assertions are the originals.
 *
 * The failure mode is a map selecting through its own mechanism instead of the
 * shared filter grammar, so the map and the chips disagree about what is on
 * screen. It renders perfectly and says the wrong thing.
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import FootprintPanel from './FootprintPanel.jsx';

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

const ROWS = [
  { client_id: 2004, states: ['GA', 'SC'], priceable_states: ['GA', 'SC'] },
  { client_id: 2001, states: ['GA', 'NC', 'SC'], priceable_states: ['GA', 'SC'] },
];

function draw(filters = {}) {
  const onFilter = vi.fn();
  render(<FootprintPanel rows={ROWS} filters={filters} onFilter={onFilter} />);
  return { onFilter };
}

describe('the map filters the book', () => {
  it('writes the shared state filter rather than holding its own selection', async () => {
    const { onFilter } = draw();
    await userEvent.click(within(screen.getByTestId('map')).getByRole('button', { name: 'NC' }));
    expect(onFilter).toHaveBeenCalledWith({ state: 'NC' });
  });

  it('toggles a state off when it is already selected', async () => {
    const { onFilter } = draw({ state: 'NC' });
    await userEvent.click(within(screen.getByTestId('map')).getByRole('button', { name: 'NC' }));
    expect(onFilter).toHaveBeenCalledWith({ state: '' });
  });

  it('keeps held-but-unpriceable states visually distinct', () => {
    // NC has payroll and no authored pack: a real gap in statutory coverage.
    draw();
    const map = within(screen.getByTestId('map'));
    expect(map.getByRole('button', { name: 'GA' })).toHaveAttribute('data-priced', 'true');
    expect(map.getByRole('button', { name: 'NC' })).toHaveAttribute('data-priced', 'false');
  });

  it('offers every state anyone in the book operates in', () => {
    // The union, not one client's footprint: the map filters the whole book.
    draw();
    const map = within(screen.getByTestId('map'));
    ['GA', 'NC', 'SC'].forEach((code) => {
      expect(map.getByRole('button', { name: code })).toBeInTheDocument();
    });
  });
});

describe('the state list beside the map', () => {
  function stateRow(code) {
    return screen.getByRole('row', { name: new RegExp(`^${code}\\b`) });
  }

  it('counts clients per state', () => {
    draw();
    expect(within(stateRow('GA')).getAllByRole('cell')[1]).toHaveTextContent('2');
    expect(within(stateRow('NC')).getAllByRole('cell')[1]).toHaveTextContent('1');
  });

  it('shows no per-state dollar figure', () => {
    // A per-state money total would double-count or credit a state that did
    // not earn it.
    draw();
    expect(stateRow('GA').textContent).not.toMatch(/\$/);
    expect(stateRow('NC').textContent).not.toMatch(/\$/);
  });

  it('names the coverage gap in words, not only as a shade', () => {
    draw();
    expect(stateRow('GA')).toHaveTextContent('Priced');
    expect(stateRow('NC')).toHaveTextContent('No authored statute');
  });

  it('writes the same filter the map does', async () => {
    const { onFilter } = draw();
    await userEvent.click(within(stateRow('NC')).getByRole('button', { name: 'NC' }));
    expect(onFilter).toHaveBeenCalledWith({ state: 'NC' });
  });
});
