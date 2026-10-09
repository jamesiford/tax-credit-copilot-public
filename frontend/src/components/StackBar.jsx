import { Layers, Plus, TrendingUp } from 'lucide-react';
import { MAX_STACK } from '../lib/whatIf.js';

/**
 * The toolbar over any list the What-if stack is fed from (28–29 Sep): add the
 * ticked rows, how many are stacked, and the way to project them.
 *
 * Shared by Near the line and a location's near-the-floor list so the two
 * read and behave as one control.
 */
export default function StackBar({ ticked = 0, onAddSelected, stackSize = 0, onOpen }) {
  const full = stackSize >= MAX_STACK;
  return (
    <div className="prox-stackbar" role="toolbar" aria-label="What-if stack">
      <button
        type="button"
        className="btn btn-secondary"
        disabled={!ticked || full}
        onClick={onAddSelected}
      >
        <Plus size={14} /> Add selected{ticked ? ` (${ticked})` : ''} to What-if
      </button>
      <span className="prox-stackbar-count">
        <Layers size={14} />
        {stackSize
          ? <><b>{stackSize}</b> in the What-if stack</>
          : 'The What-if stack is empty'}
        {full ? ` — ${MAX_STACK} is the most one projection stacks` : ''}
      </span>
      <button type="button" className="btn btn-primary" disabled={!stackSize} onClick={onOpen}>
        <TrendingUp size={14} /> {stackSize > 1 ? `Project all ${stackSize}` : 'Project'} in What-if →
      </button>
    </div>
  );
}
