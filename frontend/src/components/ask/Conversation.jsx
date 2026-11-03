import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { planLabels } from '../../lib/evidenceRoutes.js';
import AgentBadge from '../AgentBadge.jsx';
import EmptyState from '../ui/EmptyState.jsx';
import Button from '../ui/Button.jsx';

const SUGGESTIONS = [
  'Show me our Georgia Jobs Tax Credit eligibility.',
  'How did our Georgia net-new headcount move year over year?',
  'What Georgia credits might we still qualify for that we are not yet claiming?',
  'What if we hired 5 more people in Atlanta next month?',
  'Walk me through how you got that number.',
];

function Intro({ onSend }) {
  return (
    <div className="ask-intro">
      {/* Two questions every viewer has, answered before they ask. */}
      <p className="ask-note">
        <b>What it can answer.</b> Five things: eligibility, the credit portfolio,
        discovery, a what-if, and &ldquo;how did you get that number&rdquo;. Anything
        else and it says so rather than guessing.
      </p>
      <p className="ask-note">
        <b>What it reads.</b> Only the output of the deterministic tools, never the
        payroll rows and never the model&rsquo;s own arithmetic. Python computes the
        figure and hands the agent a JSON brief; the agent puts it into a sentence.
        That is why a number here matches the screen behind it.
      </p>
      <h3 className="ask-intro-title">Start with one of these</h3>
      <ul className="ask-suggest">
        {SUGGESTIONS.map((s) => (
          <li key={s}>
            <button type="button" className="ask-suggest-btn" onClick={() => onSend(s)}>{s}</button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function PlanStrip({ plan }) {
  const using = planLabels(plan.intents);
  if (!using.length && !plan.needsClient.length) return null;
  return (
    <p className="ask-plan" aria-label="Plan">
      {using.length ? <><b>Using:</b> {using.join(' · ')}</> : null}
      {plan.needsClient.length ? (
        <span className="ask-plan-needs">
          {using.length ? ' · ' : ''}Needs a client selected: {planLabels(plan.needsClient).join(' · ')}
        </span>
      ) : null}
    </p>
  );
}

function Clarify({ message, streaming, onChoose }) {
  const { clarify } = message;
  return (
    <div className="chat-clarify" role="group" aria-label="Which client?">
      {clarify.choices.map((choice, i) => (
        <button
          key={choice.client_id}
          type="button"
          className="chat-clarify-choice"
          disabled={streaming || choice.tax_year == null || clarify.answered != null}
          title={choice.tax_year == null ? 'No calculation has reached this client yet' : undefined}
          onClick={() => onChoose(message, choice)}
        >
          <span aria-hidden="true" className="ask-num">{i + 1})</span>
          {choice.name}
          {choice.tax_year != null ? <span className="chat-clarify-year"> · TY{choice.tax_year}</span> : null}
        </button>
      ))}
    </div>
  );
}

function Turn({ message, streaming, onChoose }) {
  if (message.role === 'plan') return <PlanStrip plan={message.plan} />;
  if (message.role === 'user') {
    return <div className="ask-user">{message.text}</div>;
  }
  return (
    <div className="ask-assistant">
      {message.agent ? <AgentBadge agent={message.agent} /> : null}
      <div className="chat-md ask-card">
        {message.text ? (
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.text}</ReactMarkdown>
        ) : (
          <span className="ask-muted">…</span>
        )}
      </div>
      {message.clarify ? <Clarify message={message} streaming={streaming} onChoose={onChoose} /> : null}
    </div>
  );
}

/**
 * The left pane: the turns, a plan strip per question, the numbered
 * clarification, the composer with its suggested prompts, and the states.
 * It renders; `useAskSession` decides.
 */
export default function Conversation({ session, listRef }) {
  const {
    messages, input, setInput, streaming, activeAgent, problem, send, choose,
  } = session;

  return (
    <section className="ask-convo" aria-label="Conversation">
      <div className="ask-scroll" ref={listRef}>
        {messages.length === 0 && !problem ? <Intro onSend={send} /> : null}
        <ul className="ask-turns" aria-live="polite" aria-relevant="additions">
          {messages.map((m, i) => (
            <li key={i} className={`ask-turn ask-turn-${m.role}`}>
              <Turn message={m} streaming={streaming} onChoose={choose} />
            </li>
          ))}
        </ul>
        {streaming ? (
          <p className="ask-streaming" role="status">
            <span className="ask-agent-dot ask-agent-active" aria-hidden="true" />
            {activeAgent ? 'Working…' : 'Planning…'}
          </p>
        ) : null}
        {problem ? (
          <EmptyState
            title="The assistant is unavailable"
            action={<Button onClick={problem.retry}>Try again</Button>}
          >
            The page still shows the engine&apos;s figures, and nothing was changed.
            <br />
            {problem.detail}
          </EmptyState>
        ) : null}
      </div>

      <form
        className="ask-composer"
        onSubmit={(e) => { e.preventDefault(); send(); }}
      >
        <label className="sr-only" htmlFor="ask-input">Ask Copilot</label>
        <input
          id="ask-input"
          data-autofocus
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about a credit, a county, a what-if…"
          disabled={streaming}
          autoComplete="off"
        />
        <Button type="submit" variant="primary" disabled={streaming || !input.trim()} loading={streaming}>
          Send
        </Button>
      </form>
      <p className="ask-foot">
        <button
          type="button"
          className="tcc-link"
          onClick={() => setInput('Which client and tax year is this answer about, and which tools did you use?')}
        >
          Need clarification?
        </button>
        <span> Ask what an answer is based on.</span>
      </p>
    </section>
  );
}
