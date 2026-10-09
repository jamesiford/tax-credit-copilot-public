import React, { useEffect, useRef, useState } from 'react';
import { Send, Loader2, MessageSquare, RefreshCw } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { streamChat } from '../api.js';
import AgentBadge from './AgentBadge.jsx';

const SUGGESTIONS = [
  'Show me our Georgia Jobs Tax Credit eligibility.',
  'How did our Georgia net-new headcount move year over year?',
  'What Georgia credits might we still qualify for that we are not yet claiming?',
  'What if we hired 5 more people in Atlanta next month?',
  'Walk me through how you got that number.',
];

export default function ChatPanel({ onTrail, queuedPrompt, queuedScope, onQueuedConsumed, scope }) {
  const [messages, setMessages] = useState([]);  // [{ role, agent?, text }]
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [activeAgent, setActiveAgent] = useState(null);
  const scrollRef = useRef(null);
  const abortRef = useRef(null);
  const lastQueuedRef = useRef(null);
  //: A conversation is ABOUT something. Asking from a row on the book pins the
  //: client for the whole conversation, not just the message that set it.
  const [pin, setPin] = useState(null);

  const shellScope = {
    state: scope?.jurisdiction || scope?.state || null,
    clientId: scope?.clientId && scope.clientId !== 'portfolio' ? scope.clientId : null,
    taxYear: scope?.year ?? null,
    method: new URLSearchParams(window.location.search).get('method') || 'min_max',
  };

  // DERIVED, not an effect. Clearing the pin in a `useEffect` keyed on the
  // shell scope looked right and was not: those values change after mount as
  // the shell resolves — undefined then 'portfolio' — so the effect fired once
  // on ordinary load and wiped a pin the user had just set. The first answer
  // still worked, because it used the override directly; every follow-up
  // arrived with no client and was refused.
  //
  // Only an explicit, DIFFERENT client in the scope bar outranks the pin.
  // Portfolio scope names no client, so it cannot displace one.
  const pinOutranked = (
    pin != null
    && shellScope.clientId != null
    && String(shellScope.clientId) !== String(pin.clientId)
  );
  const pinnedScope = pinOutranked ? null : pin;
  const chatScope = { ...shellScope, ...(pinnedScope || {}) };

  useEffect(() => {
    // Optional-CALLED: jsdom implements no scrollTo on elements, and `?.` on
    // the ref alone guards null rather than a missing method.
    scrollRef.current?.scrollTo?.({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, activeAgent]);

  useEffect(() => {
    if (!queuedPrompt) return;
    if (streaming) return;
    if (lastQueuedRef.current === queuedPrompt) return;
    lastQueuedRef.current = queuedPrompt;
    send(queuedPrompt, queuedScope);
    if (onQueuedConsumed) onQueuedConsumed();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queuedPrompt, streaming]);

  async function send(text, scopeOverride, { confirmed = false, shown = null } = {}) {
    const msg = (text ?? input).trim();
    if (!msg || streaming) return;
    if (scopeOverride) setPin(scopeOverride);
    const sendScope = { ...chatScope, ...(scopeOverride || {}) };
    // The model needs a referent for "their" and "since then". Sent as prior
    // turns rather than re-stated by the user.
    const prior = messages.filter((m) => m.text).map((m) => ({ role: m.role, text: m.text }));
    // A picked choice is the reader's reply, so it is what shows and what the
    // next turn's "their" points back at. The question it answers is re-sent
    // underneath rather than repeated on screen.
    const history = (shown ? [...prior, { role: 'user', text: shown }] : prior).slice(-8);
    setInput('');
    setMessages((m) => [...m, { role: 'user', text: shown || msg }]);
    setStreaming(true);
    setActiveAgent(null);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamChat(msg, (ev) => {
        if (ev.event === 'agent_start') {
          const agent = ev.data.agent;
          setActiveAgent(agent);
          setMessages((m) => [...m, { role: 'assistant', agent, text: '' }]);
        } else if (ev.event === 'token') {
          setMessages((m) => {
            const next = m.slice();
            const last = next[next.length - 1];
            if (last && last.role === 'assistant' && last.agent === ev.data.agent) {
              next[next.length - 1] = { ...last, text: last.text + ev.data.content };
            }
            return next;
          });
        } else if (ev.event === 'agent_end') {
          // Keep the badge visible; just stop pulsing.
        } else if (ev.event === 'calculation_trail') {
          if (onTrail) onTrail(ev.data);
        } else if (ev.event === 'clarify') {
          // Attach the choices to the question they answer: the last message
          // from the orchestrator, which carries the question's text.
          setMessages((m) => {
            const next = m.slice();
            const last = next[next.length - 1];
            if (last && last.role === 'assistant') {
              next[next.length - 1] = { ...last, clarify: ev.data };
            }
            return next;
          });
        } else if (ev.event === 'done') {
          setActiveAgent(null);
        }
      }, controller.signal, sendScope, history, { confirmed });
    } catch (e) {
      setMessages((m) => [...m, { role: 'assistant', agent: 'OrchestratorAgent', text: `Error: ${e.message}` }]);
    } finally {
      setStreaming(false);
      setActiveAgent(null);
      abortRef.current = null;
    }
  }

  function clearChat() {
    if (abortRef.current) {
      try { abortRef.current.abort(); } catch { /* noop */ }
      abortRef.current = null;
    }
    setMessages([]);
    setInput('');
    setActiveAgent(null);
    setStreaming(false);
    // A new conversation is about nothing yet. Keeping the pin would answer
    // the first question about whoever the LAST conversation was about.
    setPin(null);
  }

  return (
    <section className="flex min-h-0 flex-col rounded-2xl border border-subtle-2 bg-white shadow-tile">
      <div className="flex items-center gap-2 border-b border-subtle-2 px-4 py-3">
        <MessageSquare className="h-4 w-4 text-brand" strokeWidth={1.5} />
        <h2 className="text-sm font-semibold text-brand">Chat</h2>
        <button
          type="button"
          onClick={clearChat}
          disabled={messages.length === 0 && !streaming}
          title="Start a new chat"
          className="ml-2 inline-flex items-center gap-1 rounded-full border border-subtle-2 bg-subtle px-2.5 py-1 text-xs font-medium text-brand transition hover:border-brand/40 hover:bg-white disabled:cursor-not-allowed disabled:opacity-40"
        >
          <RefreshCw className="h-3 w-3" strokeWidth={1.75} />
          New chat
        </button>
        <div className="ml-auto">
          {activeAgent && <AgentBadge agent={activeAgent} active />}
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4">
        {messages.length === 0 && (
          <div className="space-y-3">
            {/* Two questions every viewer has, answered before they ask. */}
            <div className="rounded-xl border border-subtle-2 bg-subtle px-3 py-2.5 text-xs leading-relaxed text-muted">
              <b className="text-brand-ink">What it can answer.</b> Five things:
              eligibility, the credit portfolio, discovery, a what-if, and
              &ldquo;how did you get that number&rdquo;. Anything else and it says so
              rather than guessing.
              <br />
              <b className="text-brand-ink">What it reads.</b> Only the output of
              the deterministic tools — never the payroll rows and never the model’s
              own arithmetic. Python computes the figure and hands the agent a JSON
              brief; the agent puts it into a sentence. That is why a number here
              matches the screen behind it.
            </div>
            <p className="text-sm text-muted">
              Start with one of these:
            </p>
            <ul className="space-y-2">
              {SUGGESTIONS.map((s) => (
                <li key={s}>
                  <button
                    type="button"
                    onClick={() => send(s)}
                    className="w-full rounded-xl border border-subtle-2 bg-subtle px-3 py-2 text-left text-sm text-brand-ink transition hover:border-brand/40 hover:bg-white"
                  >
                    {s}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <ul className="space-y-3">
          {messages.map((m, i) => (
            <li key={i} className={m.role === 'user' ? 'flex justify-end' : 'flex'}>
              {m.role === 'user' ? (
                <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-brand px-3 py-2 text-sm text-white shadow-tile">
                  {m.text}
                </div>
              ) : (
                <div className="max-w-[90%] space-y-1">
                  {m.agent && <AgentBadge agent={m.agent} />}
                  <div className="chat-md rounded-2xl rounded-bl-sm border border-subtle-2 bg-subtle px-3 py-2 text-sm leading-relaxed text-brand-ink">
                    {m.text ? (
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text}</ReactMarkdown>
                    ) : (
                      <span className="text-muted">…</span>
                    )}
                  </div>
                  {m.clarify ? (
                    <div className="chat-clarify" role="group" aria-label="Which client?">
                      {m.clarify.choices.map((choice) => (
                        <button
                          key={choice.client_id}
                          type="button"
                          className="chat-clarify-choice"
                          disabled={streaming || choice.tax_year == null || m.clarify.answered}
                          title={choice.tax_year == null ? 'No calculation has reached this client yet' : undefined}
                          onClick={() => {
                            setMessages((all) => all.map((x) => (x === m ? { ...x, clarify: { ...x.clarify, answered: choice.client_id } } : x)));
                            send(
                              m.clarify.message,
                              { clientId: choice.client_id, taxYear: choice.tax_year },
                              { confirmed: true, shown: choice.name },
                            );
                          }}
                        >
                          {choice.name}
                          {choice.tax_year != null ? <span className="chat-clarify-year"> · TY{choice.tax_year}</span> : null}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              )}
            </li>
          ))}
        </ul>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
        className="flex items-center gap-2 border-t border-subtle-2 p-3"
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about a credit, a county, a what-if…"
          disabled={streaming}
          className="flex-1 rounded-xl border border-subtle-2 bg-subtle px-3 py-2 text-sm placeholder-muted focus:border-brand focus:bg-white focus:outline-none"
        />
        <button
          type="submit"
          disabled={streaming || !input.trim()}
          className="inline-flex items-center gap-1 rounded-xl bg-brand px-3 py-2 text-sm font-semibold text-white transition hover:bg-brand-deep disabled:opacity-40"
        >
          {streaming ? <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.5} /> : <Send className="h-4 w-4" strokeWidth={1.5} />}
          Send
        </button>
      </form>
    </section>
  );
}
