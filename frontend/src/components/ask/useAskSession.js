import { useCallback, useEffect, useRef, useState } from 'react';
import { chatEventRouter, streamChat } from '../../api.js';
import { addEvidence } from '../../lib/evidence.js';

/**
 * The conversation: what was said, what the platform answered with, and what it
 * is ABOUT. Everything the retired ChatPanel did, minus its markup.
 *
 * Rules carried over, because each was a bug once:
 *
 *  - A conversation is ABOUT something. Asking from a row pins that client for
 *    the whole conversation, not just the message that set it. The pin is
 *    DERIVED against the shell scope, never cleared in an effect: those values
 *    change after mount as the shell resolves, and an effect wiped a pin the
 *    reader had just set. Only a different, explicit client in the scope bar
 *    outranks it; portfolio scope names no client, so it cannot displace one.
 *  - History travels with the request so "their" resolves. It is context for
 *    ROUTING only; every figure still comes from a tool.
 *  - A picked clarification is the reader's reply and re-asks the original,
 *    confirmed.
 *  - A new chat is about nothing yet, so it drops the pin.
 */
export default function useAskSession({ scope, queuedPrompt, queuedScope, onQueuedConsumed, onTrail }) {
  const [messages, setMessages] = useState([]); // user | assistant | plan
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [activeAgent, setActiveAgent] = useState(null);
  const [pin, setPin] = useState(null);
  const [evidence, setEvidence] = useState([]);
  const [plan, setPlan] = useState(null);
  const [problem, setProblem] = useState(null); // { detail, retry }
  const [droppedBlocks, setDroppedBlocks] = useState(0);
  const abortRef = useRef(null);
  const lastQueuedRef = useRef(null);

  const shellScope = {
    state: scope?.jurisdiction || scope?.state || null,
    clientId: scope?.clientId && scope.clientId !== 'portfolio' ? scope.clientId : null,
    taxYear: scope?.year ?? null,
    method: new URLSearchParams(window.location.search).get('method') || 'min_max',
  };
  const pinOutranked = (
    pin != null
    && shellScope.clientId != null
    && String(shellScope.clientId) !== String(pin.clientId)
  );
  const pinnedScope = pinOutranked ? null : pin;
  const chatScope = { ...shellScope, ...(pinnedScope || {}) };

  const send = useCallback(async (text, scopeOverride, { confirmed = false, shown = null } = {}) => {
    const msg = (text ?? input).trim();
    if (!msg || streaming) return;
    if (scopeOverride) setPin(scopeOverride);
    const sendScope = { ...chatScope, ...(scopeOverride || {}) };
    const prior = messages.filter((m) => m.text).map((m) => ({ role: m.role, text: m.text }));
    const history = (shown ? [...prior, { role: 'user', text: shown }] : prior).slice(-8);
    setInput('');
    setProblem(null);
    setMessages((m) => [...m, { role: 'user', text: shown || msg }]);
    setStreaming(true);
    setActiveAgent(null);

    const controller = new AbortController();
    abortRef.current = controller;

    const onEvent = chatEventRouter({
      plan: (data) => {
        const next = {
          intents: Array.isArray(data.intents) ? data.intents : [],
          needsClient: Array.isArray(data.needs_client) ? data.needs_client : [],
        };
        setPlan(next);
        setMessages((m) => [...m, { role: 'plan', plan: next }]);
      },
      agentStart: ({ agent }) => {
        setActiveAgent(agent);
        setMessages((m) => [...m, { role: 'assistant', agent, text: '' }]);
      },
      token: ({ agent, content }) => {
        setMessages((m) => {
          const next = m.slice();
          const last = next[next.length - 1];
          if (last && last.role === 'assistant' && last.agent === agent) {
            next[next.length - 1] = { ...last, text: last.text + content };
          }
          return next;
        });
      },
      trail: (data) => onTrail?.(data),
      clarify: (data) => {
        // Attach the choices to the question they answer: the last message from
        // the orchestrator, which carries the question's text.
        setMessages((m) => {
          const next = m.slice();
          const last = next[next.length - 1];
          if (last && last.role === 'assistant') next[next.length - 1] = { ...last, clarify: data };
          return next;
        });
      },
      evidence: (item, { dropped }) => {
        setEvidence((all) => addEvidence(all, item));
        if (dropped) setDroppedBlocks((n) => n + dropped);
      },
      done: () => setActiveAgent(null),
    });

    try {
      if (import.meta.env.DEV && new URLSearchParams(window.location.search).get('askFixture') === '1') {
        // Dev builds only: the bundler drops this branch, and the fixtures with
        // it, from a production build.
        const { fixtureStream } = await import('../../lib/askFixtures.js');
        await fixtureStream(msg, onEvent);
      } else {
        await streamChat(msg, onEvent, controller.signal, sendScope, history, { confirmed });
      }
    } catch (e) {
      if (e?.name !== 'AbortError') {
        setProblem({
          detail: e?.message || String(e),
          retry: () => send(msg, scopeOverride, { confirmed, shown }),
        });
      }
    } finally {
      setStreaming(false);
      setActiveAgent(null);
      abortRef.current = null;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [input, streaming, messages, chatScope.clientId, chatScope.taxYear, chatScope.state, chatScope.method, pin, onTrail]);

  // A queued prompt (an "Ask" link, a row button) is consumed once, when idle.
  useEffect(() => {
    if (!queuedPrompt || streaming) return;
    if (lastQueuedRef.current === queuedPrompt) return;
    lastQueuedRef.current = queuedPrompt;
    send(queuedPrompt, queuedScope);
    onQueuedConsumed?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queuedPrompt, streaming]);

  const newChat = useCallback(() => {
    if (abortRef.current) {
      try { abortRef.current.abort(); } catch { /* noop */ }
      abortRef.current = null;
    }
    setMessages([]);
    setInput('');
    setActiveAgent(null);
    setStreaming(false);
    setPin(null);
    setEvidence([]);
    setPlan(null);
    setProblem(null);
    setDroppedBlocks(0);
  }, []);

  const choose = useCallback((message, choice) => {
    setMessages((all) => all.map((x) => (
      x.clarify === message.clarify ? { ...x, clarify: { ...x.clarify, answered: choice.client_id } } : x
    )));
    send(
      message.clarify.message,
      { clientId: choice.client_id, taxYear: choice.tax_year },
      { confirmed: true, shown: choice.name },
    );
  }, [send]);

  return {
    messages, input, setInput, streaming, activeAgent, evidence, plan, problem, droppedBlocks,
    chatScope, send, newChat, choose,
  };
}
