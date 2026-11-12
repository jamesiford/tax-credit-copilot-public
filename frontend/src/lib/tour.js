/**
 * The guided tour, built from the book that is actually loaded.
 *
 * A tour that names clients goes stale the moment the data changes, and on a customer's book it
 * walks to clients that do not exist. So a stop is chosen by ROLE from the portfolio rows
 * (the client with the most identified credit, one that is on the line, one that is declining)
 * and is left out when no client plays that role. Nothing here quotes a figure: the screen the
 * stop opens holds the figures, and they are the ones read from the data.
 *
 * The scripted reference-data walk lives in `demoTour.js` and loads only in a demo build.
 */

import { ALL_PROGRAMS, PORTFOLIO } from './scopeDimension.js';

export const TOUR_DEFAULT_DWELL_MS = 16_000;

const SKIP = new Set(['unavailable', 'not_assessed']);

function usable(rows) {
  return (rows || []).filter((r) => r && r.client_id != null && !r.data_unavailable && !SKIP.has(r.priority_band));
}

function byIdentified(rows) {
  return [...rows].sort((a, b) => Number(b.identified_usd || 0) - Number(a.identified_usd || 0));
}

function scopeFor(row) {
  return { clientId: row.client_id, programCode: row.program_code || ALL_PROGRAMS, year: row.tax_year ?? null };
}

function nameOf(row) {
  return row.client_name || `Client ${row.client_id}`;
}

/** The stops this book can support, in the order the argument needs them. */
export function buildTour(rows) {
  const live = usable(rows);
  if (!(rows || []).length) return [];
  const steps = [{
    view: 'trend',
    title: 'Across the book',
    scope: { clientId: PORTFOLIO, programCode: ALL_PROGRAMS, year: null },
    summary:
      'Every client the source lists, ranked by the reason to call them rather than by a score. '
      + 'Unavailable clients are named as unavailable and are never counted as having nothing to find.',
  }];
  const top = byIdentified(live.filter((r) => Number(r.identified_usd) > 0))[0];
  if (top) {
    steps.push({
      view: 'trend',
      title: `What it is worth: ${nameOf(top)}`,
      scope: scopeFor(top),
      summary:
        'The client with the most identified credit in this book. Each location is a block, each tax year a '
        + 'row, and every figure is read from the stored calculation, not recomputed on the page.',
    }, {
      view: 'eligibility',
      title: `Who qualifies: ${nameOf(top)}`,
      summary:
        'Both statutory methods run over the same payroll and are shown side by side, because the method '
        + 'changes the answer. Open an employee to see the calculation that decided them.',
      dwell_ms: 20_000,
    });
  }
  const line = byIdentified(live.filter((r) => r.priority_band === 'on_the_line'))[0];
  if (line) {
    steps.push({
      view: 'trend',
      title: `On the line: ${nameOf(line)}`,
      scope: scopeFor(line),
      summary:
        'A client within a job of a threshold, in jobs rather than dollars: one hire from a credit, or one '
        + 'departure from losing one. Who is close, and what closes the gap, is on this page.',
    });
  }
  const declining = byIdentified(live.filter((r) => r.priority_band === 'declining'))[0];
  if (declining) {
    steps.push({
      view: 'trend',
      title: `Declining: ${nameOf(declining)}`,
      scope: scopeFor(declining),
      summary:
        'Headcount has been falling across years in which this client earned credit. This is a forecast '
        + 'about a year nobody has filed yet, not a finding about a return.',
    });
  }
  if (top) {
    steps.push({
      view: 'ingestion',
      title: 'What came in',
      scope: scopeFor(top),
      summary:
        'Source rows, the rows the run selected and the exclusions, each named and counted. Nothing is '
        + 'silently dropped and nothing is repaired.',
    });
  }
  return steps;
}

/** The steps for this session: the scripted demo in a demo build, otherwise the book-driven tour. */
export async function loadTourSteps(rows) {
  if (import.meta.env.VITE_DEMO_TOUR) {
    const { DEMO_TOUR_STEPS } = await import('./demoTour.js');
    return DEMO_TOUR_STEPS;
  }
  return buildTour(rows);
}
