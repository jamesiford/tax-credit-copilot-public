import './shell.css';

/**
 * The page frame: a skip link, one `<header>` landmark holding the top bar and
 * the drill trail, and the `<main>` the skip link targets.
 *
 * It owns landmarks and nothing else. What goes in the bar, which trail shows
 * and what the page is are the caller's, so this has no idea which routes exist.
 * `children` render after `<main>` (tour bar, chat drawer, launcher).
 *
 * Never: render a second `<main>`, or put the trail outside the header (a
 * reader skipping to content would then land below it, and a screen reader
 * would announce it as unrelated to the bar).
 */
export default function AppShell({ header, mainLabel, main, children }) {
  return (
    <div className="tcc-app">
      <a className="shell-skip" href="#main-content">Skip to content</a>
      <header className="shell-header">{header}</header>
      <main id="main-content" className="tcc-main" aria-label={mainLabel} tabIndex={-1}>
        {main}
      </main>
      {children}
    </div>
  );
}
