import { useRef, useState } from 'react';
import { MessageSquare, RefreshCw, X } from 'lucide-react';
import { methodLabel } from '../../lib/reviewMeta.js';
import Button from '../ui/Button.jsx';
import MetaLine from '../ui/MetaLine.jsx';
import Tabs from '../ui/Tabs.jsx';
import Conversation from './Conversation.jsx';
import EvidencePane from './EvidencePane.jsx';
import useAskSession from './useAskSession.js';
import useMediaQuery from './useMediaQuery.js';
import useModal from './useModal.js';
import './ask.css';

/**
 * Ask Copilot: a split workspace, conversation on the left and platform-rendered
 * evidence on the right.
 *
 * It overlays the page (about 60% of the width from 1280px; the whole width
 * below that, where the evidence pane sits behind a tab). The page behind keeps
 * its scope and its scroll position: the workspace only reads them, and says
 * what the conversation is ABOUT in its header.
 *
 * It stays MOUNTED while closed so the conversation survives a close; it draws
 * nothing then. The model narrates and the engine calculates: nothing in the
 * right pane is model prose, and nothing here computes a figure.
 */
export default function AskWorkspace({
  open, onClose, scope, nameFor, onNavigate, pagePrompt = null,
  queuedPrompt = null, queuedScope = null, onQueuedConsumed, onTrail, onConfirm, onCancel,
}) {
  const session = useAskSession({ scope, queuedPrompt, queuedScope, onQueuedConsumed, onTrail });
  const wide = useMediaQuery('(min-width: 1280px)');
  const [view, setView] = useState('convo');
  const dialogRef = useRef(null);
  useModal(dialogRef, { open, onClose });

  if (!open) return null;

  const { chatScope, evidence, plan, messages, streaming } = session;
  const hasClient = chatScope.clientId != null;
  const about = [
    {
      label: 'Client',
      value: hasClient ? (nameFor?.(chatScope.clientId) || `Account ${chatScope.clientId}`) : 'All clients',
    },
    { label: 'Tax year', value: chatScope.taxYear != null ? `TY${chatScope.taxYear}` : null },
    { label: 'Method', value: methodLabel(chatScope.method) },
  ];
  const evidenceScope = { clientId: chatScope.clientId, year: chatScope.taxYear, method: chatScope.method };

  const convo = <Conversation session={session} />;
  const pane = (
    <EvidencePane
      items={evidence}
      plan={plan}
      scope={evidenceScope}
      dropped={session.droppedBlocks}
      onNavigate={onNavigate}
      onConfirm={onConfirm}
      onCancel={onCancel}
    />
  );

  return (
    <div className="ask-overlay">
      <div className="ask-scrim" aria-hidden="true" onClick={onClose} />
      <div
        ref={dialogRef}
        className="ask-workspace"
        role="dialog"
        aria-modal="true"
        aria-labelledby="ask-title"
      >
        <header className="ask-head">
          <div className="ask-head-row">
            <h2 id="ask-title" className="ask-title">
              <MessageSquare size={18} aria-hidden="true" /> Ask Copilot
            </h2>
            <div className="ask-head-actions">
              {pagePrompt ? (
                <Button size="sm" onClick={() => session.send(pagePrompt)} disabled={streaming}>
                  Ask about this page
                </Button>
              ) : null}
              <Button
                size="sm"
                icon={<RefreshCw size={14} />}
                onClick={session.newChat}
                disabled={messages.length === 0 && !streaming}
                title="Start a new chat"
              >
                New chat
              </Button>
              <Button size="sm" variant="ghost" onClick={onClose} aria-label="Close" icon={<X size={16} />} />
            </div>
          </div>
          <MetaLine items={about} className="ask-about" />
        </header>

        {wide ? (
          <div className="ask-body ask-body-split">{convo}{pane}</div>
        ) : (
          <div className="ask-body">
            <Tabs
              tabs={[
                { id: 'convo', label: 'Conversation' },
                { id: 'evidence', label: 'Evidence', count: evidence.length },
              ]}
              active={view}
              onChange={setView}
              label="Workspace"
              idPrefix="ask-view"
            />
            <div
              role="tabpanel"
              id={`ask-view-panel-${view}`}
              aria-labelledby={`ask-view-tab-${view}`}
              className="ask-stack"
            >
              {view === 'convo' ? convo : pane}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
