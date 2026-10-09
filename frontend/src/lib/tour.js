/**
 * The guided tour — the demo, encoded.
 *
 * Four value propositions in the order they have to land, and the order is the
 * argument: nothing else is worth showing until the calculation is trusted.
 *
 *   1. Who qualifies, provable down to one employee   (the trust anchor)
 *   2. How am I doing                                  (the operating model)
 *   3. What would change it                            (the lever)
 *   4. Where the money is across the book              (the scale)
 *
 * Stops carry `scope` rather than a persona. The old tour switched who you were
 * pretending to be; this one switches which client and year you are looking at,
 * because that is the dimension this product actually moves in.
 *
 * The split between clients is deliberate and honest. The reference client is real
 * payroll reconciled with the partner, and it holds ONE fiscal year with no prior
 * year — so it can prove the calculation and cannot answer "am I on track".
 * The synthetic clients carry six-year windows and real base years, so they
 * can. Saying so is stronger than blurring it.
 *
 * Kept in step with `stakeholder-docs/_john-review-script.md`. The tour previews
 * the argument that script walks, so a stop here that contradicts an act there
 * is a bug in one of them — most likely this one, because the script is read
 * against the running app and this is not.
 */

import { ALL_PROGRAMS, PORTFOLIO } from './scopeDimension.js';

export const TOUR_DEFAULT_DWELL_MS = 16_000;

/** The reference client. Real payroll, de-identified, certified. */
const REFERENCE = 1001;
/** Over-claimed TY2022. The exposure case. */
const CASCADE = 2001;
/** Threshold-crossing synthetic client — the "you could have claimed" case. */
const IRONBRIDGE = 2003;

export const TOUR_STEPS = [
  {
    view: 'trend',
    title: 'What it is worth',
    scope: { clientId: REFERENCE, programCode: 'GA_JTC', year: 2023 },
    summary:
      'Candle Bottle \u2014 a restaurant and store chain. Real client payroll, de-identified at source '
      + 'and read live from the Fabric lakehouse: 384,433 rows, 10,236 employees. 539 qualify under '
      + 'Min-Max and 656 under Pay Period \u2014 the method changes the answer, and you can see why. '
      + 'It shows no credit because we hold a single fiscal year, and net-new needs a prior one to '
      + 'measure against. The product declined to invent a base year.',
  },
  {
    view: 'ingestion',
    title: 'What came in',
    summary:
      '384,433 source rows; 384,418 selected. The selection stage names the window it used \u2014 '
      + '2023-07-28 to 2024-08-02, read from the client\u2019s own fiscal rule. The 15 exclusions are named '
      + 'and counted. Nothing is silently dropped, and nothing is repaired.',
  },
  {
    view: 'eligibility',
    title: 'Eligibility',
    summary:
      '10,236 employees evaluated. 539 clear the Min-Max test, 656 clear Pay Period. '
      + 'Two independent denominators, two independently validated lists \u2014 not one number with a caveat.',
  },
  {
    view: 'eligibility',
    title: 'Whose fiscal year is it?',
    summary:
      'The window came from Candle Bottle\u2019s own records \u2014 a 53-week payroll calendar, not a setting we chose. '
      + 'Because it spans two calendar years the labelling convention changes the answer: TY2023 by the year it '
      + 'begins, TY2024 by the year it ends. We read the regulation one way and flagged it unconfirmed.',
    dwell_ms: 20_000,
  },
  {
    view: 'onezero',
    title: 'Monthly employment: from people to headcount',
    summary:
      'The bridge between "539 people" and an average headcount the statute recognises: every eligible employee '
      + 'allocated to a unit, a legal entity and a month. Click any month to see who is in it.',
  },
  {
    view: 'eligibility',
    title: 'Down to one employee',
    summary:
      'Employee 48685377 works a full year either way. Min-Max divides by 50.86 weeks and gets $627.85 a week '
      + '\u2014 eight dollars under the floor, ineligible. Pay Period divides by 48 and gets $665.22 \u2014 eligible. '
      + 'Same paychecks, same statute. That is why both methods run and reconcile.',
    dwell_ms: 20_000,
  },
  {
    view: 'compare',
    title: 'Back-test against the independent reference calculation',
    summary:
      'Stage-by-stage reconciliation against the partner\u2019s Access output. Where the two agree, and where they do not \u2014 '
      + 'shown by stage, so a divergence names the step that caused it.',
  },
  {
    view: 'evidence',
    title: 'Audit trail',
    summary:
      'The certified figures recomputed from the lakehouse rather than from the reconciliation extract, '
      + 'with the Delta version they were read at. A source that does not reproduce them is refused, not shown.',
    dwell_ms: 20_000,
  },
  {
    view: 'eligibility',
    title: 'Same engine, different client',
    scope: { clientId: IRONBRIDGE, programCode: 'GA_JTC', year: 2024 },
    summary:
      'Ironbridge Logistics, TY2024: 124 evaluated on a calendar fiscal year, against a $686 wage floor rather '
      + 'than $636 \u2014 because a different tax year is a different rule pack, and Georgia\u2019s lowest-wage county '
      + 'moved from Glascock to Taliaferro. Nothing here was configured for this client.',
    dwell_ms: 20_000,
  },
  {
    view: 'trend',
    title: 'How am I doing, and who is near the line',
    summary:
      'This question needs a prior year, and the reference client has only one \u2014 so it runs on a synthetic client '
      + 'that has six. Run the calculation on the months that have closed: on track, or not. Then who is close, and '
      + 'what actually closes the gap \u2014 hours and wages fail independently, so "work them more" is not offered to '
      + 'somebody already at forty hours who is simply paid too little.',
    dwell_ms: 20_000,
  },
  {
    view: 'trend',
    title: 'What would change it',
    summary:
      'Four levers against the real engine \u2014 hire, lose, hours, wages. A projection is still a statutory figure, '
      + 'so it runs under the same rules and refuses a year with no authored statute.',
  },
  {
    view: 'trend',
    title: 'Exposure, not just opportunity',
    scope: { clientId: CASCADE, programCode: ALL_PROGRAMS, year: 2022 },
    summary:
      'Against an illustrative $95,000 claim we can substantiate $31,185. Surfaced as exposure rather '
      + 'than quietly dropped \u2014 an audit that reports only recoverable dollars is not an audit. The '
      + 'claimed figure is ours, not the client\u2019s; what is real is what we can substantiate.',
  },
  {
    view: 'trend',
    title: 'Across the book',
    scope: { clientId: PORTFOLIO, programCode: ALL_PROGRAMS, year: 2024 },
    summary:
      'Five clients, every program-year they hold payroll for: $1.41M recoverable and $63,815 of exposure, '
      + 'never netted against each other. Both are measured against illustrative claims, so read them as '
      + 'shape rather than as a number \u2014 what is real is the identified side each is derived from.',
  },
  {
    view: 'trend',
    title: 'Targeting',
    summary:
      'The clients closest to a threshold, ranked by the gap in jobs \u2014 because the gap in dollars is zero for '
      + 'all of them, and ranking by value would bury exactly the client worth calling.',
  },
];
