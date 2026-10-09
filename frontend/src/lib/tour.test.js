/**
 * The guided tour is the run of show, encoded.
 *
 * It drifted because nothing checked it: the tour previewed an argument the
 * script no longer made, and the only way to notice was to sit through both.
 * These tests pin the shape and the order, not the prose.
 */
import { describe, it, expect } from 'vitest';
import { TOUR_STEPS, TOUR_DEFAULT_DWELL_MS } from './tour.js';
import { ALL_PROGRAMS, PORTFOLIO } from './scopeDimension.js';

/** Every view the shell can render. Must match `NAV` in App.jsx, plus the
 *  route-only ids the pages resolve to. */
const VIEWS = new Set([
  'trend', 'eligibility', 'onezero',
  'ingestion', 'agents', 'compare',
  'rules', 'assumptions', 'evidence',
]);

describe('the guided tour', () => {
  it('only visits views the shell can actually render', () => {
    for (const step of TOUR_STEPS) {
      expect(VIEWS.has(step.view), `unknown view: ${step.view}`).toBe(true);
    }
  });

  it('gives every stop something to say', () => {
    for (const step of TOUR_STEPS) {
      expect(step.title?.length, `missing title on ${step.view}`).toBeGreaterThan(0);
      expect(step.summary?.length, `missing summary on ${step.view}`).toBeGreaterThan(40);
    }
  });

  it('follows the run of show act by act', () => {
    // Acts 2 -> 3 -> 4 -> 5 -> 6 -> 7 of _john-review-script.md. If you reorder
    // the script, reorder this; a tour that previews a different argument than
    // the one you then walk is worse than no tour.
    //
    // Six stops now read `trend`: position, progress and plan were absorbed by
    // the client and portfolio pages, so those acts are sections of one page
    // rather than destinations. The ARGUMENT is unchanged — the walk is.
    expect(TOUR_STEPS.map((step) => step.view)).toEqual([
      'trend',                                       // Act 0/1 — what it is worth
      'ingestion',                                   // Act 2 — what came in
      'eligibility', 'eligibility', 'onezero', 'eligibility', // Act 3
      'compare', 'evidence',                         // Act 4 — prove it
      'eligibility',                                 // Act 5.0 — the switch was real
      'trend',                                       // Act 5.1 / 5.2 — verdict, then the cohort
      'trend',                                       // Act 6 — what would change it
      'trend', 'trend', 'trend',                     // Act 7 — across the book
    ]);
  });

  it('switches client exactly where the script does, and never switches back', () => {
    // The reviewer sees Candle Bottle, then Ironbridge, then Cascade, then the
    // portfolio. Going backwards would land a sealed view on the wrong client.
    const switches = TOUR_STEPS.filter((step) => step.scope).map((step) => step.scope.clientId);
    expect(switches).toEqual([1001, 2003, 2001, PORTFOLIO]);
  });

  it('opens on the certified client-year so the sealed views agree with the scope', () => {
    expect(TOUR_STEPS[0].scope).toEqual({ clientId: 1001, programCode: 'GA_JTC', year: 2023 });
  });

  it('rolls the book up across every program, not just the one in scope', () => {
    const portfolio = TOUR_STEPS.find((step) => step.scope?.clientId === PORTFOLIO);
    expect(portfolio.scope.programCode).toBe(ALL_PROGRAMS);
  });

  it('runs long enough to read but short enough to sit through', () => {
    const total = TOUR_STEPS.reduce(
      (sum, step) => sum + (step.dwell_ms ?? TOUR_DEFAULT_DWELL_MS), 0,
    );
    expect(total).toBeGreaterThan(3 * 60_000);
    expect(total).toBeLessThan(6 * 60_000);
  });
});
