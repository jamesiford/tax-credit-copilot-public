/**
 * Position view: render smoke tests.
 *
 * These exist because of a pattern. Seven times on this project a change has
 * produced a screen that looked fine and was wrong — a stale value under a new
 * heading, a total that covered rows not on screen, one client's figures under
 * another's name. None threw. None failed a unit test. Every one was found by
 * a human opening the page.
 *
 * The unit tests in `coverage.test.js` prove the arithmetic. These prove the
 * component actually PUTS that arithmetic on screen, and keeps putting the
 * right one there while props change underneath it. Three of the four bugs
 * reproduced below were live in this file's subject within the last two days.
 */
import { render as renderBare, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import PositionView from './PositionView.jsx';
import { PORTFOLIO } from '../lib/scopeDimension.js';
import * as api from '../api.js';

/**
 * The client filter lives in the query string like every other filter, so the
 * view needs a router. Wrapped here rather than at seventeen call sites, and
 * `rerender` is wrapped too or a re-render would drop the router.
 */
function render(ui, options) {
  const wrapped = renderBare(<MemoryRouter>{ui}</MemoryRouter>, options);
  return {
    ...wrapped,
    rerender: (next) => wrapped.rerender(<MemoryRouter>{next}</MemoryRouter>),
  };
}

const SCOPE_OPTIONS = {
  clients: [
    { account_id: 1001, name: 'Candle Bottle', synthetic: false },
    { account_id: 2001, name: 'Cascade Retail Partners', synthetic: true },
  ],
};

const cell = (overrides = {}) => ({
  client_id: 2001,
  program_code: 'GA_JTC',
  tax_year: 2023,
  status: 'assessed',
  provenance: 'computed',
  provenance_verified: true,
  identified_usd: '140000',
  claimed_usd: '0',
  certified_usd: '0',
  variance_usd: '140000',
  opportunity_usd: '140000',
  outcome: 'unclaimed',
  is_exposure: false,
  ...overrides,
});

/** An account payload: `cells`, no `clients`. */
const accountPayload = (cells, totals = {}) => ({
  client_id: 2001,
  cells,
  engagements: [],
  totals: {
    identified_usd: '140000', claimed_usd: '0',
    opportunity_usd: '140000', exposure_usd: '0',
    cells: cells.length, exposure_cells: 0, unverified_cells: 0,
    ...totals,
  },
});

/** A portfolio payload: `clients`, no `cells`. The shapes are NOT interchangeable. */
const portfolioPayload = (clients) => ({
  clients,
  totals: {
    identified_usd: '0', claimed_usd: '0',
    opportunity_usd: '0', exposure_usd: '0',
    cells: 0, exposure_cells: 0, unverified_cells: 0,
  },
});

const scopeFor = (clientId) => ({
  clientId, programCode: 'all', year: 2023, windowMode: false,
});

/**
 * Read one KPI card by its label.
 *
 * Scoped deliberately: "Recoverable" and "Exposure" are BOTH a KPI label and a
 * grid column header, and a bare text query would match either. A test that can
 * be satisfied by the wrong element is not testing what it claims to.
 */
const kpi = (label) => {
  const strip = document.querySelector('.tcc-stat-row');
  const card = [...strip.querySelectorAll('.tcc-stat')]
    .find((c) => c.querySelector('.tcc-stat-label')?.textContent === label);
  if (!card) throw new Error(`no stat card labelled "${label}"`);
  return card;
};

beforeEach(() => {
  vi.spyOn(api, 'fetchPortfolioCoverage').mockResolvedValue(portfolioPayload([]));
  vi.spyOn(api, 'fetchClientCoverage').mockResolvedValue(accountPayload([cell()]));
  vi.spyOn(api, 'assessClient').mockResolvedValue({ assessed: [], declined: [] });
});

afterEach(() => vi.restoreAllMocks());

// ------------------------------------------------------------- it renders


describe('the view renders at both scopes', () => {
  it('shows the account grid for one client', async () => {
    render(
      <PositionView
        scope={scopeFor(2001)}
        scopeWindow={[2023]}
        scopeOptions={SCOPE_OPTIONS}
      />,
    );

    expect(await screen.findByText(/Cascade Retail Partners/)).toBeInTheDocument();
    expect(await screen.findByText('$140k')).toBeInTheDocument();
    expect(screen.getByText('TY2023')).toBeInTheDocument();
  });

  it('shows the portfolio matrix across clients', async () => {
    api.fetchPortfolioCoverage.mockResolvedValue(portfolioPayload([
      {
        client_id: 2001,
        cells: [cell()],
        totals: { opportunity_usd: '140000', exposure_usd: '0', cells: 1, exposure_cells: 0, unverified_cells: 0 },
      },
    ]));

    render(
      <PositionView
        scope={scopeFor(PORTFOLIO)}
        scopeWindow={[2023]}
        scopeOptions={SCOPE_OPTIONS}
      />,
    );

    expect(await screen.findByText('The book')).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: /Cascade Retail Partners/ })).toBeInTheDocument();
  });
});

// ------------------------------------------------ absence is not a zero


describe('a client nobody has assessed is still in the book', () => {
  it('lists the unassessed client and offers the run', async () => {
    api.fetchPortfolioCoverage.mockResolvedValue(portfolioPayload([
      {
        client_id: 2001,
        cells: [cell()],
        totals: { opportunity_usd: '140000', exposure_usd: '0', cells: 1, exposure_cells: 0, unverified_cells: 0 },
      },
    ]));

    render(
      <PositionView scope={scopeFor(PORTFOLIO)} scopeWindow={[2023]} scopeOptions={SCOPE_OPTIONS} />,
    );

    // Candle Bottle has no claim record, so coverage does not mention it.
    const row = (await screen.findByRole('button', { name: /Candle Bottle/ })).closest('tr');
    expect(within(row).getByText('Not assessed')).toBeInTheDocument();
    // And it must not have acquired a dollar figure on the way in.
    expect(within(row).queryByText(/\$/)).not.toBeInTheDocument();
  });

  it('assesses that client and re-reads coverage', async () => {
    api.fetchPortfolioCoverage.mockResolvedValue(portfolioPayload([
      {
        client_id: 2001,
        cells: [cell()],
        totals: { opportunity_usd: '140000', exposure_usd: '0', cells: 1, exposure_cells: 0, unverified_cells: 0 },
      },
    ]));

    render(
      <PositionView scope={scopeFor(PORTFOLIO)} scopeWindow={[2023]} scopeOptions={SCOPE_OPTIONS} />,
    );
    await userEvent.click(await screen.findByRole('button', { name: /Run assessment/ }));

    await waitFor(() => expect(api.assessClient).toHaveBeenCalledWith(1001));
    await waitFor(() => expect(api.fetchPortfolioCoverage).toHaveBeenCalledTimes(2));
  });
});

// --------------------------------------------------- the seven-times bug


describe('a payload never renders under the wrong scope', () => {
  it('does not crash when the scope changes before the fetch resolves', async () => {
    // The B4 crash, exactly. React renders before effects run, so switching
    // from portfolio to account gave AccountGrid a payload with `clients` and
    // no `cells`, and `cells.forEach` took the page down.
    api.fetchPortfolioCoverage.mockResolvedValue(portfolioPayload([
      { client_id: 2001, cells: [cell()], totals: { opportunity_usd: '140000', exposure_usd: '0', cells: 1 } },
    ]));

    const { rerender } = render(
      <PositionView scope={scopeFor(PORTFOLIO)} scopeWindow={[2023]} scopeOptions={SCOPE_OPTIONS} />,
    );
    await screen.findByText('The book');

    expect(() => rerender(
      <PositionView scope={scopeFor(2001)} scopeWindow={[2023]} scopeOptions={SCOPE_OPTIONS} />,
    )).not.toThrow();

    expect(await screen.findByText(/Cascade Retail Partners/)).toBeInTheDocument();
  });

  it('never shows the previous client\'s figures under a new client\'s name', async () => {
    // The B3 stale-facts bug, in the view rather than the scope bar. A cold
    // Fabric read is ~55s; showing the old numbers for that long under a new
    // heading is the same error as showing them forever.
    let release;
    api.fetchClientCoverage.mockImplementation((clientId) => {
      if (clientId === 1001) {
        return new Promise((resolve) => { release = () => resolve(accountPayload([
          cell({ client_id: 1001, opportunity_usd: '999', variance_usd: '999', identified_usd: '999' }),
        ], { opportunity_usd: '999' })); });
      }
      return Promise.resolve(accountPayload([cell()], { opportunity_usd: '140000' }));
    });

    const { rerender } = render(
      <PositionView scope={scopeFor(2001)} scopeWindow={[2023]} scopeOptions={SCOPE_OPTIONS} />,
    );
    // Scoped to the KPI so the row total's identical figure cannot satisfy it.
    await waitFor(() => expect(kpi('Recoverable')).toHaveTextContent('$140,000'));

    // Switch client. The fetch for 1001 has NOT resolved yet.
    rerender(
      <PositionView scope={scopeFor(1001)} scopeWindow={[2023]} scopeOptions={SCOPE_OPTIONS} />,
    );

    await waitFor(() => {
      expect(screen.getByText(/Candle Bottle/)).toBeInTheDocument();
    });
    // The heading changed, so the figures must not still be Cascade's.
    expect(document.body).not.toHaveTextContent('$140,000');

    release();
    await waitFor(() => expect(kpi('Recoverable')).toHaveTextContent('$999'));
  });
});

// ------------------------------------------------- totals match the grid


describe('the headline describes what is on screen', () => {
  it('totals reconcile with the cells rendered', async () => {
    // The other B4 bug: the KPI said $388,605 over six cells while the grid
    // showed one column, because the fetch ignored the scope window. A headline
    // covering years that are not visible invites exactly the question you do
    // not want in front of a client.
    const cells = [
      cell({ tax_year: 2022, opportunity_usd: '100000', variance_usd: '100000' }),
      cell({ tax_year: 2023, opportunity_usd: '40000', variance_usd: '40000' }),
    ];
    api.fetchClientCoverage.mockResolvedValue(
      accountPayload(cells, { opportunity_usd: '140000', cells: 2 }),
    );

    render(
      <PositionView scope={scopeFor(2001)} scopeWindow={[2022, 2023]} scopeOptions={SCOPE_OPTIONS} />,
    );

    await screen.findByText('TY2022');
    expect(screen.getByText('TY2023')).toBeInTheDocument();
    expect(kpi('Recoverable')).toHaveTextContent('$140,000');

    // Cells assessed must equal the columns shown, or the headline covers
    // years the grid is not displaying.
    expect(kpi('Cells assessed')).toHaveTextContent('2');
    expect(screen.getAllByRole('columnheader').filter((h) => /^TY/.test(h.textContent))).toHaveLength(2);
  });

  it('requests exactly the window it is asked to render', async () => {
    render(
      <PositionView
        scope={scopeFor(2001)}
        scopeWindow={[2020, 2021, 2022]}
        scopeOptions={SCOPE_OPTIONS}
      />,
    );

    await waitFor(() => expect(api.fetchClientCoverage).toHaveBeenCalled());
    expect(api.fetchClientCoverage).toHaveBeenCalledWith(2001, { taxYears: [2020, 2021, 2022] });
  });
});

describe('the book filters by client, and says what it hid', () => {
  const book = () => {
    api.fetchPortfolioCoverage.mockResolvedValue(portfolioPayload([
      {
        client_id: 2001,
        cells: [cell()],
        totals: { opportunity_usd: '140000', exposure_usd: '0', cells: 1, exposure_cells: 0, unverified_cells: 0 },
      },
      {
        client_id: 1001,
        cells: [cell()],
        totals: { opportunity_usd: '10000', exposure_usd: '0', cells: 1, exposure_cells: 0, unverified_cells: 0 },
      },
    ]));
    return render(
      <PositionView scope={scopeFor(PORTFOLIO)} scopeWindow={[2023]} scopeOptions={SCOPE_OPTIONS} />,
    );
  };

  it('narrows to the clients that match', async () => {
    book();
    await screen.findByText('Cascade Retail Partners');

    await userEvent.click(screen.getByRole('button', { name: /Filter Client/ }));
    await userEvent.type(screen.getByLabelText('Contains'), 'candle');
    await userEvent.click(screen.getByRole('button', { name: 'Apply' }));

    expect(screen.getByText('Candle Bottle')).toBeInTheDocument();
    expect(screen.queryByText('Cascade Retail Partners')).not.toBeInTheDocument();
  });

  it('states the denominator, because a forgotten filter is a wrong total', async () => {
    book();
    await screen.findByText('Cascade Retail Partners');

    await userEvent.click(screen.getByRole('button', { name: /Filter Client/ }));
    await userEvent.type(screen.getByLabelText('Contains'), 'candle');
    await userEvent.click(screen.getByRole('button', { name: 'Apply' }));

    expect(screen.getByText(/Showing 1 of \d+ clients/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Clear all/ })).toBeInTheDocument();
  });

  it('says nothing at all when nothing is filtered', async () => {
    book();
    await screen.findByText('Cascade Retail Partners');
    expect(screen.queryByText(/^Showing/)).not.toBeInTheDocument();
  });
});

// ------------------------------------------------------ exposure surfaces


describe('exposure is never quietly absorbed', () => {
  it('shows a banner and a separate total', async () => {
    api.fetchClientCoverage.mockResolvedValue(accountPayload(
      [cell({
        status: 'claimed', outcome: 'over_claimed', is_exposure: true,
        identified_usd: '100000', claimed_usd: '140000',
        variance_usd: '-40000', opportunity_usd: '0',
      })],
      { opportunity_usd: '0', exposure_usd: '40000', exposure_cells: 1 },
    ));

    render(
      <PositionView scope={scopeFor(2001)} scopeWindow={[2023]} scopeOptions={SCOPE_OPTIONS} />,
    );

    expect(await screen.findByText(/claimed above what we compute as substantiated/)).toBeInTheDocument();
    expect(screen.getByText('Over-claimed')).toBeInTheDocument();
    // Negative, so money at risk cannot read as money owed.
    expect(screen.getByText('-$40k')).toBeInTheDocument();
  });

  it('shows opportunity and exposure as two figures, not one net', async () => {
    api.fetchClientCoverage.mockResolvedValue(accountPayload(
      [
        cell({ tax_year: 2022, opportunity_usd: '40000', variance_usd: '40000' }),
        cell({
          tax_year: 2023, status: 'claimed', outcome: 'over_claimed', is_exposure: true,
          identified_usd: '100000', claimed_usd: '140000',
          variance_usd: '-40000', opportunity_usd: '0',
        }),
      ],
      { opportunity_usd: '40000', exposure_usd: '40000', exposure_cells: 1, cells: 2 },
    ));

    render(
      <PositionView scope={scopeFor(2001)} scopeWindow={[2022, 2023]} scopeOptions={SCOPE_OPTIONS} />,
    );

    // Netted, both would read zero and the client would look like nothing to
    // discuss. Both figures must be present and non-zero.
    const cards = await screen.findAllByText('$40,000');
    expect(cards.length).toBeGreaterThanOrEqual(2);
  });
});

// ------------------------------------------------------------- provenance


describe('unverified figures stay visibly distinct', () => {
  it('badges a client-asserted claim', async () => {
    api.fetchClientCoverage.mockResolvedValue(accountPayload([
      cell({ provenance: 'client_asserted', provenance_verified: false }),
    ], { unverified_cells: 1 }));

    render(
      <PositionView scope={scopeFor(2001)} scopeWindow={[2023]} scopeOptions={SCOPE_OPTIONS} />,
    );

    expect(await screen.findByText('unverified')).toBeInTheDocument();
  });

  it('does not badge a computed one', async () => {
    render(
      <PositionView scope={scopeFor(2001)} scopeWindow={[2023]} scopeOptions={SCOPE_OPTIONS} />,
    );

    await screen.findByText('$140k');
    expect(screen.queryByText('unverified')).not.toBeInTheDocument();
  });
});

// --------------------------------------------------------------- declines


describe('declined years are named, not omitted', () => {
  it('lists what could not be calculated after an assessment', async () => {
    api.assessClient.mockResolvedValue({
      assessed: [],
      declined: [{
        program_code: 'GA_JTC', tax_year: 2026,
        reason: 'no_authored_statute',
        detail: 'No rule pack for GA_JTC tax year 2026.',
      }],
    });

    render(
      <PositionView scope={scopeFor(2001)} scopeWindow={[2023]} scopeOptions={SCOPE_OPTIONS} />,
    );
    await screen.findByText('$140k');

    await userEvent.click(screen.getByRole('button', { name: /Run assessment/ }));

    expect(await screen.findByText(/GA_JTC TY2026/)).toBeInTheDocument();
    expect(screen.getByText(/No rule pack for GA_JTC tax year 2026/)).toBeInTheDocument();
  });
});

// ------------------------------------------------------------ empty states


describe('empty is stated, not implied', () => {
  it('says nothing is assessed rather than rendering a blank grid', async () => {
    api.fetchClientCoverage.mockResolvedValue(accountPayload([], { cells: 0, opportunity_usd: '0' }));

    render(
      <PositionView scope={scopeFor(2001)} scopeWindow={[2023]} scopeOptions={SCOPE_OPTIONS} />,
    );

    expect(await screen.findByText(/Nothing assessed for this client yet/)).toBeInTheDocument();
  });

  it('surfaces a failed fetch instead of showing an empty grid', async () => {
    api.fetchClientCoverage.mockRejectedValue(new Error('claims 503 · store unavailable'));

    render(
      <PositionView scope={scopeFor(2001)} scopeWindow={[2023]} scopeOptions={SCOPE_OPTIONS} />,
    );

    expect(await screen.findByText(/store unavailable/)).toBeInTheDocument();
  });
});
