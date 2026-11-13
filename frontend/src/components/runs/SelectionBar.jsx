import { Play, X } from 'lucide-react';
import Button from '../ui/Button.jsx';
import { runLabel, selectionCount, selectionLabel } from '../../lib/runBatches.js';
import './runs.css';

/**
 * The persistent bar that appears once something is selected: how many, "select all N matching" when the book holds
 * more than the page, and the actions. It is a labelled region with a polite live count, so a screen reader hears the
 * count change as rows are picked, and focus never moves by itself. When "all matching" cannot be handed to the
 * server (the filter has no server equivalent) the bar says why instead of approximating.
 */
export default function SelectionBar({ selection, matching, onSelectMatching, onClear, onRun }) {
  const count = selectionCount(selection);
  if (count === 0) return null;
  const showAll = !selection.matching && matching && (matching.count == null || matching.count > count);
  return (
    <section className="runs-selbar" aria-label="Selected clients">
      <span className="runs-selcount" role="status" aria-live="polite">
        {selectionLabel(selection)}
      </span>
      {showAll && matching.ok ? (
        <Button size="sm" variant="link" onClick={onSelectMatching}>
          {matching.count == null ? 'Select all matching the filters' : `Select all ${matching.count} matching`}
        </Button>
      ) : null}
      {showAll && !matching.ok ? (
        <span className="small muted">All matching cannot be selected at once. {matching.reason}</span>
      ) : null}
      <span className="runs-selspacer" />
      <Button size="sm" variant="ghost" icon={<X size={14} />} onClick={onClear}>Clear</Button>
      <Button id="run-selection-open" size="sm" variant="primary" icon={<Play size={14} />} onClick={onRun}>
        {runLabel(selection)}
      </Button>
    </section>
  );
}
