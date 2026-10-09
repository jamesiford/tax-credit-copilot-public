/**
 * Brand configuration — the ONE place a deployment's name and logo come
 * from. [WL-1]
 *
 * The default is the neutral "Tax Credit Copilot" brand, shipped with this
 * repo. A customer overlay sets `VITE_BRAND_*` at build time (see
 * `overlays/README.md`) to replace the name and logo without touching any
 * component. Only variables prefixed `VITE_` are exposed to client code
 * (see `frontend/.env.example`).
 *
 * The colour palette is a SEPARATE half of white-labeling: see the `brand`,
 * `accent-2` and `success` tokens in `tailwind.config.js`. Both default to
 * the same neutral brand so an un-overlaid build looks consistent.
 */

export const brand = {
  name: import.meta.env?.VITE_BRAND_NAME ?? 'Tax Credit Copilot',
  shortName: import.meta.env?.VITE_BRAND_SHORT_NAME ?? 'TCC',
  logoSrc: import.meta.env?.VITE_BRAND_LOGO ?? '/brand-mark.svg',
  faviconSrc: import.meta.env?.VITE_BRAND_FAVICON ?? '/brand-mark.svg',
};

export default brand;
