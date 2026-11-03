/*
 * Why: an inset assessment ("here is what we found") that sits inside a page
 * without competing with it. The dot is decoration; the title carries meaning,
 * so colour is never the only signal.
 * Never: use brand blue for a verdict, or put the verdict in the dot alone.
 */
import { useId } from 'react';
import './Callout.css';

const TONES = ['neutral', 'above-min', 'below-min', 'partial', 'base-year'];

export default function Callout({ title, tone = 'neutral', children }) {
  const titleId = useId();
  const safeTone = TONES.includes(tone) ? tone : 'neutral';

  return (
    <div
      role="note"
      className={`ui-callout ui-callout-${safeTone}`}
      aria-labelledby={title ? titleId : undefined}
    >
      {title && (
        <p className="ui-callout-title" id={titleId}>
          <span className="ui-callout-dot" aria-hidden="true" />
          {title}
        </p>
      )}
      <div className="ui-callout-body">{children}</div>
    </div>
  );
}
