/**
 * Scope bar: render smoke tests.
 *
 * `scopeDimension.test.js` proves the reconciliation rules. This proves the bar
 * SHOWS them — and, specifically, that it never shows a fact belonging to a
 * different selection.
 *
 * The bug this file exists for: switching client left the previous client's row
 * count and states on screen for the ~55 seconds of a cold Fabric read. The
 * heading said one company; the facts underneath were another's. It threw no
 * error and failed no unit test.
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import ScopeBar from './ScopeBar.jsx';
import { ALL_PROGRAMS, PORTFOLIO, reconcileScope } from '../lib/scopeDimension.js';

const OPTIONS = {
  clients: [
    { account_id: 1001, name: 'Candle Bottle', synthetic: false },
    { account_id: 2001, name: 'Cascade Retail Partners', synthetic: true },
  ],
  programs: [
    {
      program_code: 'GA_JTC',
      name: 'Georgia Jobs Tax Credit',
      jurisdiction: { level: 'state', code: 'GA', name: 'Georgia' },
      authored_years: [2020, 2021, 2022, 2023, 2024, 2025],
      calculable: true,
      not_calculable_reason: '',
    },
    {
      program_code: 'SC_JTC',
      name: 'South Carolina Jobs Tax Credit',
      jurisdiction: { level: 'state', code: 'SC', name: 'South Carolina' },
      authored_years: [],
      calculable: false,
      not_calculable_reason: 'No year-scoped rule packs authored for sc_jtc. ADR-005.',
    },
  ],
  years: { authored: [2020, 2021, 2022, 2023, 2024, 2025], latest: 2025, window_years: 6 },
};

const CASCADE = {
  account_id: 2001,
  states: ['GA', 'NC', 'SC'],
  payroll_years: [2020, 2021, 2022, 2023, 2024, 2025, 2026],
  calculable_years: [2020, 2021, 2022, 2023, 2024, 2025],
  payroll_without_statute: [2026],
  rows: 76086,
};

const CANDLE_BOTTLE = {
  account_id: 1001,
  states: ['GA'],
  payroll_years: [2023, 2024],
  calculable_years: [2023, 2024],
  payroll_without_statute: [],
  rows: 384433,
};

const scope = (overrides = {}) => ({
  clientId: PORTFOLIO, programCode: ALL_PROGRAMS, year: 2025, windowMode: false, ...overrides,
});

function renderBar(props = {}) {
  const current = props.scope || scope();
  const resolved = reconcileScope(current, OPTIONS, props.clientScope ?? null);
  const onChange = props.onChange || vi.fn();
  const utils = render(
    <ScopeBar
      options={OPTIONS}
      scope={resolved.scope}
      resolved={resolved}
      clientScope={props.clientScope ?? null}
      clientError={props.clientError ?? null}
      clientLoading={props.clientLoading ?? false}
      onChange={onChange}
      loading={props.loading ?? false}
    />,
  );
  return { ...utils, onChange, resolved };
}

const derived = () => document.querySelector('.scope-derived');

// ------------------------------------------------------------- the axes


describe('three axes render', () => {
  it('offers every client plus the portfolio', () => {
    renderBar();
    const who = screen.getByLabelText(/Who/);
    expect(within(who).getByRole('option', { name: /All clients \(2\)/ })).toBeInTheDocument();
    expect(within(who).getByRole('option', { name: /Candle Bottle/ })).toBeInTheDocument();
  });

  it('marks a synthetic tenant so a demo figure is not quoted as a client result', () => {
    renderBar();
    expect(screen.getByRole('option', { name: /Cascade Retail Partners · synthetic/ })).toBeInTheDocument();
  });

  it('disables a program with no authored years rather than hiding it', () => {
    // Hiding it would read as "no such program", which is a different and wrong
    // statement from "we cannot price it".
    renderBar();
    const option = screen.getByRole('option', { name: /South Carolina.*no authored years/ });
    expect(option).toBeDisabled();
  });

  it('offers only years the selection can actually be priced for', () => {
    renderBar({ scope: scope({ clientId: 1001 }), clientScope: CANDLE_BOTTLE });
    const when = screen.getByLabelText(/When/);
    const years = within(when).getAllByRole('option').map((o) => o.textContent);
    expect(years).toEqual(['TY2023', 'TY2024']);
  });
});

// ------------------------------------------------- jurisdiction is derived


describe('jurisdiction is shown as derived, never offered', () => {
  it('labels it derived', () => {
    renderBar();
    expect(within(derived()).getByText('derived')).toBeInTheDocument();
  });

  it('narrows to one jurisdiction when a program is chosen', () => {
    renderBar({ scope: scope({ programCode: 'GA_JTC' }) });
    expect(derived()).toHaveTextContent('GA');
    expect(derived()).not.toHaveTextContent('SC');
  });

  it('has no jurisdiction control', () => {
    // Two independent axes would let an operator select a contradiction
    // ("Georgia" + "Federal WOTC") that has no meaning.
    renderBar();
    expect(screen.queryByLabelText(/jurisdiction/i)).not.toBeInTheDocument();
    expect(screen.getAllByRole('combobox')).toHaveLength(3);
  });
});

// --------------------------------------------------- the stale-facts bug


describe('facts belong to the selected client', () => {
  it('shows the row count and states for the client in scope', () => {
    renderBar({ scope: scope({ clientId: 2001 }), clientScope: CASCADE });
    expect(derived()).toHaveTextContent('76,086 payroll rows');
    expect(derived()).toHaveTextContent('GA, NC, SC');
  });

  it('shows NOTHING while the next client is loading', () => {
    // The bug: for ~55s the bar read "Candle Bottle" above
    // "76,086 payroll rows · GA, NC, SC", which are Cascade's. Stale facts must
    // be cleared before the fetch, not after it resolves.
    renderBar({ scope: scope({ clientId: 1001 }), clientScope: null, clientLoading: true });

    expect(derived()).not.toHaveTextContent('76,086');
    expect(derived()).not.toHaveTextContent('384,433');
    expect(derived()).toHaveTextContent(/reading this client/i);
  });

  it('disables the year axis while loading so a stale year cannot be picked', () => {
    renderBar({ scope: scope({ clientId: 1001 }), clientScope: null, clientLoading: true });
    expect(screen.getByLabelText(/When/)).toBeDisabled();
  });

  it('surfaces a failed client lookup instead of rendering an empty bar', () => {
    renderBar({
      scope: scope({ clientId: 1001 }),
      clientScope: null,
      clientError: 'client scope 404 · Unknown client 1001.',
    });
    expect(derived()).toHaveTextContent('Unknown client 1001');
  });
});

// ------------------------------------------------- held but not priceable


describe('payroll we hold but cannot price is stated', () => {
  it('names the years', () => {
    // "We hold your 2026 payroll but cannot price it yet" is a real answer, and
    // silently dropping the year would make the coverage look complete.
    renderBar({ scope: scope({ clientId: 2001 }), clientScope: CASCADE });
    expect(derived()).toHaveTextContent('TY2026 held, not priceable');
  });

  it('says nothing when everything can be priced', () => {
    renderBar({ scope: scope({ clientId: 1001, year: 2024 }), clientScope: CANDLE_BOTTLE });
    expect(derived()).not.toHaveTextContent('not priceable');
  });
});

// --------------------------------------------------------- the notice


describe('an invalidated selection is announced', () => {
  it('says so when the year had to move', () => {
    // Silently recomputing under a different year's statute would be a wrong
    // number presented as a right one.
    renderBar({ scope: scope({ clientId: 1001, year: 2020 }), clientScope: CANDLE_BOTTLE });
    expect(screen.getByText(/TY2020 is not available.*moved to TY2024/)).toBeInTheDocument();
  });

  it('stays quiet when the selection is honoured', () => {
    renderBar({ scope: scope({ clientId: 1001, year: 2023 }), clientScope: CANDLE_BOTTLE });
    expect(document.querySelector('.scope-notices')).toBeNull();
  });

  it('explains a program it cannot calculate', () => {
    renderBar({ scope: scope({ programCode: 'SC_JTC' }) });
    expect(screen.getByText(/No year-scoped rule packs authored for sc_jtc/)).toBeInTheDocument();
  });
});

// ------------------------------------------------------------ interaction


describe('changing an axis reports the whole scope', () => {
  it('emits the new client', async () => {
    const { onChange } = renderBar();
    await userEvent.selectOptions(screen.getByLabelText(/Who/), '2001');
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ clientId: 2001 }));
  });

  it('emits the portfolio sentinel, not a number', async () => {
    const { onChange } = renderBar({ scope: scope({ clientId: 2001 }), clientScope: CASCADE });
    await userEvent.selectOptions(screen.getByLabelText(/Who/), PORTFOLIO);
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ clientId: PORTFOLIO }));
  });

  it('toggles the retroactive window and shows its span', async () => {
    const { onChange } = renderBar({ scope: scope({ clientId: 2001 }), clientScope: CASCADE });
    await userEvent.click(screen.getByRole('button', { name: /Window/ }));
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ windowMode: true }));

    renderBar({ scope: scope({ clientId: 2001, windowMode: true }), clientScope: CASCADE });
    expect(screen.getByRole('button', { name: '2020–2025' })).toBeInTheDocument();
  });

  it('cannot toggle a window over a single year', () => {
    renderBar({ scope: scope({ clientId: 1001, year: 2023 }), clientScope: { ...CANDLE_BOTTLE, payroll_years: [2023], calculable_years: [2023] } });
    expect(screen.getByRole('button', { name: /Window/ })).toBeDisabled();
  });
});
