import { useEffect, useState } from 'react';
import { evidenceTabs } from '../../lib/evidence.js';
import { showOnPage } from '../../lib/evidenceRoutes.js';
import MetaLine from '../ui/MetaLine.jsx';
import Tabs from '../ui/Tabs.jsx';
import ConfirmCard from './ConfirmCard.jsx';
import EvidenceBlocks from './EvidenceBlocks.jsx';

/**
 * The right-hand pane: platform-rendered evidence, never model prose.
 *
 * With evidence it is tabs (one per item, a count chip where the item holds a
 * list), the blocks, a provenance footer and the platform's disclaimer. Without
 * any (today's stream emits none) it offers a "Show on page" chip for each
 * capability the plan named, which is the same answer on the page itself.
 */

function Provenance({ provenance }) {
  if (!provenance) return null;
  return (
    <footer className="ask-provenance">
      <MetaLine
        items={[
          { label: 'Run', value: provenance.run_id },
          { label: 'Rule pack', value: provenance.rule_pack },
          { label: 'Trail hash', value: provenance.trail_hash ? <code className="ask-hash">{provenance.trail_hash}</code> : null },
          { label: 'Produced', value: provenance.produced_at },
        ]}
      />
    </footer>
  );
}

function DeepLinks({ plan, scope, onNavigate }) {
  const chips = showOnPage(plan?.intents || [], scope);
  const asked = plan?.needsClient || [];

  if (!chips.length) {
    return (
      <div className="ask-empty" role="status">
        <h3 className="ask-empty-title">No evidence yet</h3>
        <p>
          Ask a question and the figures behind the answer appear here, rendered by
          the calculation engine. Until then, every figure is on the page itself.
        </p>
      </div>
    );
  }
  return (
    <div className="ask-empty">
      <h3 className="ask-empty-title">The engine&apos;s figures are on the page</h3>
      <p>
        This answer did not come with figures of its own. Each tool it used has a
        view on the page that shows the same answer for this scope.
      </p>
      <ul className="ask-chips" aria-label="Show on page">
        {chips.map((chip) => (
          <li key={chip.label}>
            {chip.href ? (
              <a
                className="ask-chip"
                href={chip.href}
                onClick={(event) => {
                  if (event.metaKey || event.ctrlKey || event.shiftKey || event.button) return;
                  event.preventDefault();
                  onNavigate?.(chip.href);
                }}
              >
                Show {chip.label} on page
              </a>
            ) : (
              <span className="ask-chip" aria-disabled="true" title={chip.reason}>
                Show {chip.label} on page <span className="ask-chip-reason">({chip.reason})</span>
              </span>
            )}
          </li>
        ))}
      </ul>
      {asked.length ? (
        <p className="ask-note">Needs a client selected: {asked.join(', ')}.</p>
      ) : null}
    </div>
  );
}

export default function EvidencePane({
  items = [], plan = null, scope = {}, onNavigate, dropped = 0, onConfirm, onCancel, now,
}) {
  const tabs = evidenceTabs(items);
  const [active, setActive] = useState(tabs[0]?.id ?? null);

  // A new item arrives: show it. A tab that has gone (new chat) falls back.
  useEffect(() => {
    if (!tabs.length) { setActive(null); return; }
    if (!tabs.some((tab) => tab.id === active)) setActive(tabs[tabs.length - 1].id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tabs.map((t) => t.id).join('|')]);

  if (!items.length) {
    return (
      <section className="ask-pane" aria-label="Evidence">
        <DeepLinks plan={plan} scope={scope} onNavigate={onNavigate} />
      </section>
    );
  }

  const index = tabs.findIndex((tab) => tab.id === active);
  const item = items[index >= 0 ? index : 0];
  const current = tabs[index >= 0 ? index : 0];

  return (
    <section className="ask-pane" aria-label="Evidence">
      <Tabs tabs={tabs} active={current.id} onChange={setActive} label="Evidence" idPrefix="ask-ev" />
      <div
        role="tabpanel"
        id={`ask-ev-panel-${current.id}`}
        aria-labelledby={`ask-ev-tab-${current.id}`}
        className="ask-panel"
      >
        {item.kind === 'confirmation' ? (
          <ConfirmCard item={item} onConfirm={onConfirm} onCancel={onCancel} now={now} />
        ) : (
          <EvidenceBlocks blocks={item.blocks} />
        )}
        {dropped ? (
          <p className="ask-note">
            {dropped} block{dropped === 1 ? '' : 's'} from the platform did not fit the evidence contract and
            {dropped === 1 ? ' was' : ' were'} not shown.
          </p>
        ) : null}
        <Provenance provenance={item.provenance} />
        {item.disclaimer ? <p className="ask-disclaimer">{item.disclaimer}</p> : null}
      </div>
    </section>
  );
}
