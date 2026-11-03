/*
 * Why: a page greeting needs a consistent opening band so every page starts
 * from the same place and the heading level stays correct for the outline.
 *
 * Never: carry a verdict colour, replace the page's single h1 when `level`
 * says otherwise, or put actions in the title text (use the aside slot).
 */
import './HeroBand.css';

export default function HeroBand({ title, level = 1, compact = false, aside, children }) {
  const Heading = `h${Math.min(6, Math.max(1, Number(level) || 1))}`;
  const className = compact ? 'ui-hero ui-hero--compact' : 'ui-hero';

  return (
    <header className={className}>
      <div className="ui-hero__main">
        <Heading className="ui-hero__title">{title}</Heading>
        {children && <div className="ui-hero__sub">{children}</div>}
      </div>
      {aside && <div className="ui-hero__aside">{aside}</div>}
    </header>
  );
}
