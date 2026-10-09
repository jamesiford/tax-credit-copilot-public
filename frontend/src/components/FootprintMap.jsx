import { useMemo, useState } from 'react';
import { ComposableMap, Geographies, Geography } from 'react-simple-maps';

/**
 * Where a client actually operates.
 *
 * Replaces the old per-site marker map, which plotted latitude and longitude
 * from a synthetic site registry. The real source carries county and ZIP but no
 * coordinates, and inventing them to keep a nicer-looking map would be the one
 * thing this codebase does not do.
 *
 * So this shades whole states instead. It is a weaker picture and a true one,
 * and it still answers the question the map is asked in a demo: *where is this
 * workforce, and how many jurisdictions are we reasoning about?*
 *
 * Statute is state-scoped, which makes the state the honest unit anyway — a
 * marker in the middle of a county implies a precision the credit does not have.
 */

const GEO_URL = 'https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json';

const NAME_TO_CODE = {
  Alabama: 'AL', Alaska: 'AK', Arizona: 'AZ', Arkansas: 'AR', California: 'CA',
  Colorado: 'CO', Connecticut: 'CT', Delaware: 'DE', Florida: 'FL', Georgia: 'GA',
  Hawaii: 'HI', Idaho: 'ID', Illinois: 'IL', Indiana: 'IN', Iowa: 'IA',
  Kansas: 'KS', Kentucky: 'KY', Louisiana: 'LA', Maine: 'ME', Maryland: 'MD',
  Massachusetts: 'MA', Michigan: 'MI', Minnesota: 'MN', Mississippi: 'MS',
  Missouri: 'MO', Montana: 'MT', Nebraska: 'NE', Nevada: 'NV',
  'New Hampshire': 'NH', 'New Jersey': 'NJ', 'New Mexico': 'NM', 'New York': 'NY',
  'North Carolina': 'NC', 'North Dakota': 'ND', Ohio: 'OH', Oklahoma: 'OK',
  Oregon: 'OR', Pennsylvania: 'PA', 'Rhode Island': 'RI', 'South Carolina': 'SC',
  'South Dakota': 'SD', Tennessee: 'TN', Texas: 'TX', Utah: 'UT', Vermont: 'VT',
  Virginia: 'VA', Washington: 'WA', 'West Virginia': 'WV', Wisconsin: 'WI',
  Wyoming: 'WY', 'District of Columbia': 'DC',
};

export default function FootprintMap({ states = [], priced = [], selected = [], onSelect }) {
  const [hover, setHover] = useState(null);
  const present = new Set(states.map((s) => String(s).toUpperCase()));
  const pricedSet = new Set(priced.map((s) => String(s).toUpperCase()));
  const selectedSet = new Set(selected.map((s) => String(s).toUpperCase()));
  // `react-simple-maps` takes its fills as a JS prop, so the tokens are read
  // rather than restated. Writing them here as literals is how the legend and
  // the map end up disagreeing about what "priced" looks like.
  const fill = useMemo(() => {
    const style = getComputedStyle(document.documentElement);
    const token = (name, fallback) => style.getPropertyValue(name).trim() || fallback;
    return {
      priced: token('--map-priced', '#26478d'),
      held: token('--map-held', '#9db4d6'),
      empty: token('--map-empty', '#eef0f4'),
      pricedHover: token('--map-priced-hover', '#406eb3'),
      emptyHover: token('--map-empty-hover', '#e4e7ec'),
      // Selection is CHROME, not a reading, so it takes the purple accent
      // rather than a fourth shade of blue that would read as a third state.
      selected: token('--accent-2-strong', '#63197f'),
    };
  }, []);

  if (!present.size) {
    return <p className="small muted">No payroll states for this selection.</p>;
  }

  return (
    <div className="footprint-map">
      {/* `style` here is the library's PROP, not CSS: it takes default/hover/
          pressed objects and cannot be expressed as a class. */}
      <ComposableMap projection="geoAlbersUsa" width={780} height={420} className="footprint-svg">
        <Geographies geography={GEO_URL}>
          {({ geographies }) => geographies.map((geo) => {
            const code = NAME_TO_CODE[geo.properties.name];
            const has = code && present.has(code);
            // A state we hold payroll for but cannot price is a real gap in
            // statutory coverage, and it should not look like a state we can.
            const canPrice = has && pricedSet.has(code);
            const isSelected = has && selectedSet.has(code);
            const clickable = has && typeof onSelect === 'function';
            return (
              <Geography
                key={geo.rsmKey}
                geography={geo}
                role={clickable ? 'button' : undefined}
                tabIndex={clickable ? 0 : undefined}
                aria-label={clickable ? `${isSelected ? 'Clear' : 'Filter to'} ${geo.properties.name}` : undefined}
                aria-pressed={clickable ? isSelected : undefined}
                onClick={() => clickable && onSelect(code)}
                onKeyDown={(event) => {
                  if (!clickable) return;
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    onSelect(code);
                  }
                }}
                onMouseEnter={() => has && setHover(`${geo.properties.name}${canPrice ? '' : ' — no authored statute'}`)}
                onMouseLeave={() => setHover(null)}
                // The library's PROP, not CSS: default/hover/pressed objects
                // that no class can express. The fills come from tokens.
                style={{
                  default: {
                    fill: canPrice ? fill.priced : has ? fill.held : fill.empty,
                    // Selection is drawn as an OUTLINE, never as a fill. Filling
                    // it would overwrite the priced/held distinction, which is
                    // a statement about statutory coverage and the one thing
                    // this map exists to show.
                    stroke: isSelected ? fill.selected : '#fff',
                    strokeWidth: isSelected ? 2.2 : 0.6,
                    outline: 'none',
                    cursor: clickable ? 'pointer' : 'default',
                  },
                  hover: {
                    fill: has ? fill.pricedHover : fill.emptyHover,
                    stroke: isSelected ? fill.selected : '#fff',
                    strokeWidth: isSelected ? 2.2 : 0.6,
                    outline: 'none',
                    cursor: clickable ? 'pointer' : 'default',
                  },
                  pressed: { outline: 'none' },
                }}
              />
            );
          })}
        </Geographies>
      </ComposableMap>
      <div className="footprint-legend">
        <span><i className="swatch-priced" /> Priced</span>
        <span><i className="swatch-held" /> Payroll, no authored statute</span>
        {hover && <b>{hover}</b>}
      </div>
    </div>
  );
}
