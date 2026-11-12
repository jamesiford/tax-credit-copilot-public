/**
 * The tour is built from the loaded book, so it must work for any book:
 * ids and names it has never heard of, one client, and none.
 */
import { describe, it, expect } from 'vitest';
import { buildTour, loadTourSteps } from './tour.js';
import { PORTFOLIO } from './scopeDimension.js';

const row = (over) => ({
  client_id: 71, client_name: 'Example Client Q', priority_band: 'unclaimed_at_scale',
  identified_usd: '1000', program_code: 'XX_PROG', tax_year: 2031, ...over,
});

describe('the data-driven tour', () => {
  it('has no tour for an empty book', () => {
    expect(buildTour([])).toEqual([]);
  });

  it('opens on the book and then visits the client with the most identified credit', () => {
    const steps = buildTour([row({ client_id: 5, identified_usd: '10' }), row({ client_id: 9, identified_usd: '900' })]);
    expect(steps[0].scope.clientId).toBe(PORTFOLIO);
    expect(steps[1].scope).toEqual({ clientId: 9, programCode: 'XX_PROG', year: 2031 });
  });

  it('leaves out a role nobody plays rather than inventing one', () => {
    const titles = buildTour([row({})]).map((s) => s.title);
    expect(titles.some((t) => t.startsWith('On the line'))).toBe(false);
    expect(titles.some((t) => t.startsWith('Declining'))).toBe(false);
  });

  it('adds a stop for each role the book has', () => {
    const steps = buildTour([
      row({ client_id: 1 }),
      row({ client_id: 2, priority_band: 'on_the_line' }),
      row({ client_id: 3, priority_band: 'declining' }),
    ]);
    const clients = steps.filter((s) => s.scope).map((s) => s.scope.clientId);
    expect(clients).toEqual(expect.arrayContaining([PORTFOLIO, 1, 2, 3]));
  });

  it('never walks to a client whose data is unavailable', () => {
    const steps = buildTour([
      row({ client_id: 4, data_unavailable: true, priority_band: 'unavailable', identified_usd: null }),
    ]);
    expect(steps.every((s) => s.scope?.clientId !== 4)).toBe(true);
  });

  it('quotes no figure and names no client of its own', () => {
    for (const step of buildTour([row({}), row({ client_id: 2, priority_band: 'declining' })])) {
      expect(step.summary).not.toMatch(/\d{2,}/);
      expect(step.summary.length).toBeGreaterThan(40);
    }
  });

  it('uses the book-driven tour unless a demo build asks for the script', async () => {
    const steps = await loadTourSteps([row({})]);
    expect(steps[0].scope.clientId).toBe(PORTFOLIO);
    expect(steps.some((s) => s.scope?.clientId === 1001)).toBe(false);
  });
});
