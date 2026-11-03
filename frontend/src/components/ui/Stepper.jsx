/*
 * Why: a guided flow needs a visible "where am I" that is also a way to move.
 * It is route-driven, so any enabled step is activatable.
 *
 * Never: block navigation like a wizard, use the --state-* colours (selection
 * is not a verdict), or make a disabled step focusable.
 */
import './Stepper.css';

const GLYPH = { done: '✓' };

function StepBody({ step, index }) {
  return (
    <>
      <span className="ui-stepper__marker" aria-hidden="true">
        {GLYPH[step.status] ?? (step.status === 'current' ? '' : index + 1)}
      </span>
      <span className="ui-stepper__label">{step.label}</span>
      {step.status === 'done' && <span className="ui-stepper__sr">(completed)</span>}
    </>
  );
}

function StepControl({ step, index, onSelect }) {
  const body = <StepBody step={step} index={index} />;
  const enabled = step.status !== 'disabled';
  const handler = step.onSelect ?? onSelect;
  const current = step.status === 'current' ? { 'aria-current': 'step' } : {};

  if (enabled && step.href) {
    return (
      <a
        className="ui-stepper__control"
        href={step.href}
        onClick={handler ? () => handler(step.id) : undefined}
        {...current}
      >
        {body}
      </a>
    );
  }
  if (enabled && handler) {
    return (
      <button
        type="button"
        className="ui-stepper__control"
        onClick={() => handler(step.id)}
        {...current}
      >
        {body}
      </button>
    );
  }
  return (
    <span
      className="ui-stepper__control"
      aria-disabled={enabled ? undefined : 'true'}
      {...current}
    >
      {body}
    </span>
  );
}

export default function Stepper({ steps = [], label = 'Progress', onSelect }) {
  return (
    <nav aria-label={label} className="ui-stepper-nav">
      <ol className="ui-stepper">
        {steps.map((step, index) => (
          <li
            key={step.id}
            className={`ui-stepper__item ui-stepper__item--${step.status}`}
          >
            <StepControl step={step} index={index} onSelect={onSelect} />
          </li>
        ))}
      </ol>
    </nav>
  );
}
