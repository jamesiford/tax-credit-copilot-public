import { useEffect, useState } from 'react';

/**
 * `matchMedia` as state. jsdom (and any environment without it) reports a match
 * for a min-width query, i.e. the wide layout, so tests opt INTO the narrow one.
 */
export default function useMediaQuery(query) {
  const supported = typeof window !== 'undefined' && typeof window.matchMedia === 'function';
  const [matches, setMatches] = useState(() => (supported ? window.matchMedia(query).matches : true));

  useEffect(() => {
    if (!supported) return undefined;
    const list = window.matchMedia(query);
    const onChange = () => setMatches(list.matches);
    onChange();
    list.addEventListener?.('change', onChange);
    return () => list.removeEventListener?.('change', onChange);
  }, [query, supported]);

  return matches;
}
