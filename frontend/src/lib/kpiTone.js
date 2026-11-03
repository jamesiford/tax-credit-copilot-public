/**
 * Older views named a tile's reading by colour ("green", "amber"). A tile's
 * tone is a --state-* family now, named for what it means; this maps the old
 * spellings so a view can be moved over without re-deciding its readings.
 * Anything not listed (including "accent", which had no reading) is neutral.
 */
const FROM_COLOUR = { green: 'above-min', amber: 'partial', red: 'below-min' };

export function kpiTone(legacy) {
  return FROM_COLOUR[legacy] ?? 'neutral';
}
