/**
 * Priority bands — why you would call a client, and in what order.
 *
 * The backend decides the band; this file only knows how to SAY it. Keeping the
 * ranking server-side is what lets paging and sorting stay honest, and keeping
 * the wording here is what stops five components inventing five vocabularies
 * for the same five states.
 *
 * There is deliberately no numeric score. Blending dollars and jobs needs
 * coefficients nobody can justify, and the point of this ranking is that
 * somebody can read it aloud to a client.
 */

export const BANDS = {
  exposed: {
    label: 'Exposed',
    rank: 0,
    tone: 'bad',
    // What you would actually say on the call. Only reachable from a VERIFIED
    // filing: an accusation resting on somebody's unsupported word is the most
    // dangerous thing this screen could put next to a client's name.
    line: 'Claimed more than we can substantiate.',
    why: 'A finding against a filed return is a deadline somebody else controls.',
  },
  on_the_line: {
    label: 'On the line',
    rank: 1,
    tone: 'warn',
    line: 'Within one job of the threshold.',
    why: 'Which side they end on decides the whole credit.',
  },
  declining: {
    label: 'Declining',
    rank: 2,
    // NOT `bad`. `bad` is what exposure wears, and exposure is a finding
    // against a return somebody has already filed. This is a forecast about a
    // year nobody has filed yet, so it is drawn as an outline rather than a
    // fill — same urgency, visibly not the same kind of statement.
    tone: 'forecast',
    line: 'Headcount falling back toward the base year.',
    why: 'Credit already earned is being spent down every month nobody calls.',
  },
  unclaimed_at_scale: {
    label: 'Identified',
    rank: 3,
    tone: 'good',
    // Deliberately NOT "money is outstanding". Whether they already claimed it
    // is a fact about a filing we do not hold. What we can say is what the
    // engine found.
    line: 'Qualifies, and we have put a figure on it.',
    why: 'Recoverable retroactively, so it is worth more but waits better.',
  },
  not_assessed: {
    label: 'Not assessed',
    rank: 4,
    tone: 'neutral',
    line: 'We have not looked yet.',
    why: 'No figure — which is not the same as a zero.',
  },
  settled: {
    label: 'Nothing found',
    rank: 5,
    tone: 'neutral',
    // Was "Settled", which asserts a resolution. We have looked and computed
    // no credit; whether anything is outstanding against a filing is a
    // different question we cannot answer.
    line: 'Assessed, and no credit identified.',
    why: '',
  },
};

const UNKNOWN = {
  label: 'Unknown', rank: 99, tone: 'neutral',
  line: 'No band recorded.', why: '',
};

export function band(id) {
  return BANDS[id] || UNKNOWN;
}

/** Descending priority. Ascending rank IS descending priority. */
export const BAND_ORDER = Object.entries(BANDS)
  .sort((a, b) => a[1].rank - b[1].rank)
  .map(([id]) => id);

/**
 * How far from the threshold, as a sentence rather than a signed number.
 *
 * `jobs_margin` is signed on purpose — `jobs_to_threshold` clamps at zero, so
 * one job over and fifty over both read 0.0 and "about to lose eligibility"
 * cannot be told from "comfortable". Rendering the raw sign would make a
 * reader do that translation every row.
 */
export function marginReading(margin) {
  if (margin == null) return { text: 'not measured', tone: 'neutral', direction: 'unknown' };
  if (margin < 0) {
    return {
      text: `${Math.abs(margin)} to qualify`,
      tone: 'warn',
      direction: 'short',
    };
  }
  if (margin === 0) {
    return { text: 'exactly at the line', tone: 'warn', direction: 'at' };
  }
  return { text: `${margin} over`, tone: 'good', direction: 'over' };
}

/**
 * A falling headcount, as a sentence somebody can read aloud.
 *
 * Deliberately says what HAS happened and what it puts at risk, never what
 * will happen. "They will lose the credit" is a prediction this product does
 * not make; "they are two jobs above the base year they earned it from" is a
 * fact about payroll already on file.
 */
export function trendReading(trend) {
  if (!trend?.declining) return null;
  const years = trend.years_falling || 1;
  const span = years === 1 ? 'a year' : `${years} years running`;
  const fallen = Number(trend.fallen_by || 0).toFixed(1);
  return {
    // The grid gets the short form and the sentence travels as its title.
    // Neither is a summary of the other: `short` states the size of the fall,
    // `text` states its shape.
    short: `\u2193 ${fallen} jobs since TY${trend.peak_tax_year}`,
    text: `Down ${fallen} jobs from TY${trend.peak_tax_year}, falling ${span}.`,
    detail: trend.below_base
      ? 'Now below the base year the credit was earned from.'
      : 'Still above the base year, but the margin is closing.',
    tone: 'forecast',
  };
}
