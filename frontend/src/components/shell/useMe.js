import { useEffect, useState } from 'react';
import { fetchMe } from '../../api.js';

/**
 * Who is signed in, read once from `/api/me` (an endpoint the app already
 * calls; this adds none).
 *
 * `null` while loading and on any failure: the shell must never block on, or
 * show an error for, an identity it only uses to say hello.
 */
export default function useMe() {
  const [me, setMe] = useState(null);
  useEffect(() => {
    let live = true;
    fetchMe().then((who) => { if (live) setMe(who); }).catch(() => { if (live) setMe(null); });
    return () => { live = false; };
  }, []);
  return me;
}
