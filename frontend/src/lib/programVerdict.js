import { authoredYearsLabel } from './reference.js';

/**
 * What a programme's verdict card says, from facts the Programs view already
 * holds: whether statute is authored by year, and whether it is signed off.
 *
 * "Calculable" is NOT "right". It says a year pack exists, so the engine will
 * price that year under that year's rules; the sign-off is the separate pill.
 * When the shell has not told us which years are authored (`known` false) the
 * card makes no readiness claim at all, rather than guessing.
 */
export function programVerdict(rule, years = [], known = true) {
  const pills = [{ variant: 'category', label: rule.jurisdiction || 'Unscoped' }];
  let tone = 'neutral';
  let assessment = null;

  if (known && years.length > 0) {
    tone = 'above-min';
    pills.push({ variant: 'above-min', icon: 'check', label: 'Calculable' });
    assessment = `Statute is authored for ${authoredYearsLabel(years)}, so each of those years prices under the rules in force that year.`;
  } else if (known) {
    tone = 'partial';
    pills.push({ variant: 'partial', icon: 'dot', label: 'Not calculated yet' });
    assessment = 'No year pack is authored, so this program is described but refuses to calculate, by name, rather than borrowing a neighbouring year\u2019s rules.';
  }

  pills.push(rule.verified
    ? { variant: 'above-min', icon: 'check', label: 'Signed off' }
    : { variant: 'neutral', icon: 'dot', label: 'Review pending' });

  return { tone, pills, assessment };
}
