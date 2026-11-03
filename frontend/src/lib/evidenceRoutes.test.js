import { describe, expect, it } from 'vitest';
import { CATALOG, capabilityLabel, planLabels, showOnPage } from './evidenceRoutes.js';

describe('where each capability lives on the page', () => {
  it('names every capability the backend can plan', () => {
    expect(Object.keys(CATALOG).sort()).toEqual([
      'at_risk', 'book', 'discovery', 'eligibility', 'explain', 'multi_state', 'simulate', 'situation', 'trend',
    ]);
  });

  it('the plan strip lists distinct labels in plan order', () => {
    expect(planLabels(['eligibility', 'trend'])).toEqual(['Eligibility', 'Trend']);
    expect(planLabels(['multi_state', 'discovery'])).toEqual(['Programs']);
    expect(capabilityLabel('brand_new')).toBe('brand new');
  });

  it('links each capability to the matching view for the current scope', () => {
    const chips = showOnPage(
      ['eligibility', 'trend', 'at_risk', 'simulate', 'explain', 'situation'],
      { clientId: 2001, year: 2023 },
    );
    const byLabel = Object.fromEntries(chips.map((c) => [c.label, c.href]));
    expect(byLabel).toEqual({
      Eligibility: '/c/2001/eligibility?year=2023',
      Trend: '/c/2001?year=2023',
      'At risk': '/c/2001?year=2023&ctab=progress',
      'What-if': '/c/2001?year=2023&ctab=whatif',
      'Audit trail': '/c/2001/evidence?year=2023',
      Position: '/c/2001?year=2023&ctab=claimed',
    });
  });

  it('carries the method on the sections that read one', () => {
    const [chip] = showOnPage(['trend'], { clientId: 2001, year: 2023, method: 'pay_period' });
    expect(chip.href).toBe('/c/2001?year=2023&method=pay_period');
  });

  it('the book and the programs need no client', () => {
    const chips = showOnPage(['book', 'discovery'], { clientId: 'portfolio' });
    expect(chips.map((c) => [c.label, c.href, c.reason])).toEqual([
      ['The book', '/', null],
      ['Programs', '/rules', null],
    ]);
  });

  it('a client-scoped capability with no client is disabled with its reason, not hidden', () => {
    const [chip] = showOnPage(['eligibility'], { clientId: 'portfolio' });
    expect(chip).toMatchObject({ label: 'Eligibility', href: null, reason: 'Pick a client first' });
  });

  it('offers no link for a capability it does not know', () => {
    expect(showOnPage(['nonsense'], { clientId: 2001 })).toEqual([]);
  });

  it('one chip per destination', () => {
    expect(showOnPage(['multi_state', 'discovery'], {})).toHaveLength(1);
  });
});
