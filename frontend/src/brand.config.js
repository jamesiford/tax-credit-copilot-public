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

/**
 * The visual theme: a set of semantic-token assignments in
 * `src/styles/tokens/theme-*.css`, selected by `html[data-theme]`.
 *
 * `modern` is the default; `classic` is the previous look, kept so the revamp
 * can be rolled back by configuration (`VITE_THEME=classic`) rather than a
 * revert. A customer overlay does not need a third theme: it overrides semantic
 * roles in one stylesheet (see docs/design/DESIGN-SYSTEM.md).
 */
export const THEMES = ['modern', 'classic'];
export const DEFAULT_THEME = 'modern';
export const THEME_STORAGE_KEY = 'tcc-theme';

/** The configured theme, falling back to the default for anything unknown. */
export function configuredTheme() {
  const wanted = import.meta.env?.VITE_THEME;
  return THEMES.includes(wanted) ? wanted : DEFAULT_THEME;
}

/**
 * Set `data-theme` on <html>. Called from main.jsx BEFORE the first render so
 * the page never paints in one theme and flips to the other.
 *
 * A stored choice outranks the build default so the style guide's toggle (and a
 * reviewer comparing the two) survives a reload. It is a view preference, not
 * data: nothing about a client or a calculation is stored under this key.
 */
export function applyTheme(root = document.documentElement, storage = globalThis.localStorage) {
  let theme = configuredTheme();
  try {
    const stored = storage?.getItem(THEME_STORAGE_KEY);
    if (THEMES.includes(stored)) theme = stored;
  } catch {
    // Storage can be blocked; the build default is a fine answer.
  }
  root.setAttribute('data-theme', theme);
  return theme;
}

export default brand;
