import Card from './ui/Card.jsx';
import Pill from './ui/Pill.jsx';
import { shortHash, stageLabel } from '../lib/reference.js';

/**
 * The calculation trail as a stepped list: step, formula, output, citation, and
 * the hash that ties the step to its source and configuration.
 *
 * It lays out engine output; it never computes or rewrites it. Inputs,
 * parameters and output are the engine's own JSON, verbatim and in the data
 * register (never below 12px). `compact` is the printed-pack summary: the step,
 * its formula and where it came from, without the working.
 *
 * Replaces the hand-rolled `.tcc-walk` markup and the Evidence page's summary
 * table, which were the same list drawn twice.
 */

function Block({ title, value }) {
  return (
    <div className="tcc-trail-block">
      <b>{title}</b>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </div>
  );
}

function HashChip({ label, value }) {
  if (!value) return null;
  return (
    <span className="tcc-trail-hash" title={`${label}: ${value}`}>
      {label} {shortHash(value)}
    </span>
  );
}

function Step({ step, compact }) {
  const where = [stageLabel(step.stage), step.method && step.method !== 'shared' ? stageLabel(step.method) : null]
    .filter(Boolean).join(' · ');
  const assumptions = (step.assumption_ids || []).join(', ') || 'none';
  const exceptions = (step.exceptions || []).join('; ') || 'none';

  return (
    <li className="tcc-trail-step">
      <Card as="div" label={`Step ${step.step_id}`} className="tcc-trail-card">
        <p className="tcc-trail-name">
          <code>{step.step_id}</code>
          <Pill variant="category">{where}</Pill>
          {step.decision_basis ? <Pill variant="neutral">{step.decision_basis}</Pill> : null}
        </p>
        <code className="tcc-trail-formula">{step.formula}</code>
        {compact ? null : (
          <div className="tcc-trail-io">
            <Block title="Inputs" value={step.inputs} />
            <Block title="Parameters" value={step.parameters} />
            <Block title="Output" value={step.output} />
          </div>
        )}
        <p className="tcc-trail-cite">
          Assumptions: {assumptions}
          {compact ? '' : ` · Exceptions: ${exceptions}`}
          {' · '}Source: {step.citation || '—'}
          <HashChip label="source" value={step.source_hash} />
          <HashChip label="config" value={step.config_hash} />
        </p>
        {compact ? null : (
          <details className="tcc-step-proof">
            <summary>Reproducibility metadata</summary>
            <dl className="tcc-kv">
              <dt>Calculation ID</dt><dd>{step.calculation_id}</dd>
              <dt>Code</dt><dd>{step.code_ref}</dd>
              <dt>Source hash</dt><dd>{step.source_hash}</dd>
              <dt>Config hash</dt><dd>{step.config_hash}</dd>
              <dt>Timestamp</dt><dd>{step.timestamp}</dd>
            </dl>
          </details>
        )}
      </Card>
    </li>
  );
}

export default function TrailSteps({ steps = [], compact = false }) {
  if (!steps.length) return null;
  return (
    <ol className="tcc-trail" aria-label="Calculation trail">
      {steps.map((step) => <Step key={step.step_id} step={step} compact={compact} />)}
    </ol>
  );
}
