import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ChatPanel from './ChatPanel.jsx';
import * as api from '../api.js';

/**
 * A conversation is ABOUT something.
 *
 * Asking from a row on the book set the client for exactly one message and
 * then reverted to the shell scope — which at portfolio scope carries no
 * client at all. So the follow-up "what is their trend?" arrived with no
 * client and the backend correctly refused it, which read to the user as the
 * assistant forgetting who they were discussing one line after answering.
 */
const PORTFOLIO_SCOPE = { clientId: 'portfolio', year: 2025, jurisdiction: 'GA' };

beforeEach(() => {
  vi.spyOn(api, 'streamChat').mockImplementation(async (_msg, onEvent) => {
    onEvent({ event: 'agent_start', data: { agent: 'ClientSituationAgent' } });
    onEvent({ event: 'token', data: { agent: 'ClientSituationAgent', content: 'ok' } });
    onEvent({ event: 'done', data: {} });
  });
});

afterEach(() => vi.restoreAllMocks());

const scopeOf = (call) => call[3];
const historyOf = (call) => call[4];

describe('the chat remembers which client it is about', () => {
  it('pins the scope an ask arrives with, and keeps it for the follow-up', async () => {
    const { rerender } = render(
      <ChatPanel
        scope={PORTFOLIO_SCOPE}
        queuedPrompt="Brief me on Cascade"
        queuedScope={{ clientId: 2001, taxYear: 2023 }}
        onQueuedConsumed={() => {}}
      />,
    );

    await waitFor(() => expect(api.streamChat).toHaveBeenCalledTimes(1));
    expect(scopeOf(api.streamChat.mock.calls[0])).toMatchObject({ clientId: 2001, taxYear: 2023 });

    rerender(
      <ChatPanel scope={PORTFOLIO_SCOPE} queuedPrompt={null} onQueuedConsumed={() => {}} />,
    );

    await userEvent.type(screen.getByRole('textbox'), 'what is their trend?');
    await userEvent.click(screen.getByRole('button', { name: /send/i }));

    await waitFor(() => expect(api.streamChat).toHaveBeenCalledTimes(2));
    // The whole point: still 2001, not the portfolio scope's null.
    expect(scopeOf(api.streamChat.mock.calls[1])).toMatchObject({ clientId: 2001, taxYear: 2023 });
  });

  it('sends prior turns so "their" has a referent', async () => {
    render(<ChatPanel scope={{ ...PORTFOLIO_SCOPE, clientId: 2001 }} />);

    await userEvent.type(screen.getByRole('textbox'), 'brief me');
    await userEvent.click(screen.getByRole('button', { name: /send/i }));
    await waitFor(() => expect(api.streamChat).toHaveBeenCalledTimes(1));
    // Nothing has been said yet, so nothing to carry.
    expect(historyOf(api.streamChat.mock.calls[0])).toEqual([]);

    await userEvent.type(screen.getByRole('textbox'), 'and their trend?');
    await userEvent.click(screen.getByRole('button', { name: /send/i }));

    await waitFor(() => expect(api.streamChat).toHaveBeenCalledTimes(2));
    const history = historyOf(api.streamChat.mock.calls[1]);
    expect(history.map((t) => t.text)).toContain('brief me');
  });

  it('survives the shell scope resolving after the pin is set', async () => {
    // THE BUG THE FIRST FIX MISSED. Clearing the pin in a useEffect keyed on
    // scope.clientId / scope.year looked right, but those values change after
    // mount as the shell settles — undefined, then 'portfolio' and a year. So
    // the effect fired on an ordinary page load and wiped a pin the user had
    // just set. The first answer still worked because it used the override
    // directly; every follow-up arrived with no client and was refused.
    const { rerender } = render(
      <ChatPanel
        scope={{}}
        queuedPrompt="Brief me on Cascade"
        queuedScope={{ clientId: 2001, taxYear: 2025 }}
        onQueuedConsumed={() => {}}
      />,
    );
    await waitFor(() => expect(api.streamChat).toHaveBeenCalledTimes(1));

    // The shell finishes resolving. This is not a user action.
    rerender(
      <ChatPanel scope={PORTFOLIO_SCOPE} queuedPrompt={null} onQueuedConsumed={() => {}} />,
    );

    await userEvent.type(screen.getByRole('textbox'), 'any close to the threshold?');
    await userEvent.click(screen.getByRole('button', { name: /send/i }));

    await waitFor(() => expect(api.streamChat).toHaveBeenCalledTimes(2));
    expect(scopeOf(api.streamChat.mock.calls[1])).toMatchObject({ clientId: 2001 });
  });

  it('holds the pin at portfolio scope, which names no client', async () => {
    render(
      <ChatPanel
        scope={PORTFOLIO_SCOPE}
        queuedPrompt="Brief me on Cascade"
        queuedScope={{ clientId: 2001, taxYear: 2025 }}
        onQueuedConsumed={() => {}}
      />,
    );
    await waitFor(() => expect(api.streamChat).toHaveBeenCalledTimes(1));

    await userEvent.type(screen.getByRole('textbox'), 'and their trend?');
    await userEvent.click(screen.getByRole('button', { name: /send/i }));

    await waitFor(() => expect(api.streamChat).toHaveBeenCalledTimes(2));
    expect(scopeOf(api.streamChat.mock.calls[1])).toMatchObject({ clientId: 2001 });
  });

  it('drops the pin when a new chat starts', async () => {
    // A fresh conversation is about nothing yet. Keeping the pin would answer
    // the first question about whoever the last conversation was about, under
    // the new conversation's heading.
    render(
      <ChatPanel
        scope={PORTFOLIO_SCOPE}
        queuedPrompt="Brief me on Cascade"
        queuedScope={{ clientId: 2001, taxYear: 2023 }}
        onQueuedConsumed={() => {}}
      />,
    );
    await waitFor(() => expect(api.streamChat).toHaveBeenCalledTimes(1));

    await userEvent.click(screen.getByRole('button', { name: /new chat/i }));

    await userEvent.type(screen.getByRole('textbox'), 'how much is the credit?');
    await userEvent.click(screen.getByRole('button', { name: /send/i }));

    await waitFor(() => expect(api.streamChat).toHaveBeenCalledTimes(2));
    expect(scopeOf(api.streamChat.mock.calls[1]).clientId).toBeNull();
  });

  it('lets the scope bar outrank the pin', async () => {
    // Changing client in the shell is a deliberate act. A pin that survived it
    // would answer about the previous client under the new one's heading.
    const { rerender } = render(
      <ChatPanel
        scope={PORTFOLIO_SCOPE}
        queuedPrompt="Brief me on Cascade"
        queuedScope={{ clientId: 2001, taxYear: 2023 }}
        onQueuedConsumed={() => {}}
      />,
    );
    await waitFor(() => expect(api.streamChat).toHaveBeenCalledTimes(1));

    rerender(
      <ChatPanel scope={{ clientId: 1001, year: 2023, jurisdiction: 'GA' }} queuedPrompt={null} />,
    );

    await userEvent.type(screen.getByRole('textbox'), 'and their trend?');
    await userEvent.click(screen.getByRole('button', { name: /send/i }));

    await waitFor(() => expect(api.streamChat).toHaveBeenCalledTimes(2));
    expect(scopeOf(api.streamChat.mock.calls[1])).toMatchObject({ clientId: 1001 });
  });
});


describe('when the client is unclear, the chat asks — it never picks', () => {
  const CLARIFY = {
    message: 'what is their trend?',
    reason: 'does not say which client it means',
    choices: [
      { client_id: 2003, name: 'Ironbridge Logistics', tax_year: 2022 },
      { client_id: 2001, name: 'Cascade Retail Partners', tax_year: 2025 },
      { client_id: 9999, name: 'Never Run', tax_year: null },
    ],
  };

  const asking = () => api.streamChat.mockImplementationOnce(async (_msg, onEvent) => {
    onEvent({ event: 'agent_start', data: { agent: 'OrchestratorAgent' } });
    onEvent({ event: 'token', data: { agent: 'OrchestratorAgent', content: 'Which client do you mean?' } });
    onEvent({ event: 'clarify', data: CLARIFY });
    onEvent({ event: 'done', data: {} });
  });

  it('offers one button per client, with the year each would answer for', async () => {
    asking();
    render(<ChatPanel scope={PORTFOLIO_SCOPE} />);
    await userEvent.type(screen.getByRole('textbox'), 'what is their trend?');
    await userEvent.click(screen.getByRole('button', { name: /send/i }));

    const group = await screen.findByRole('group', { name: 'Which client?' });
    expect(group).toHaveTextContent('Ironbridge Logistics · TY2022');
    expect(group).toHaveTextContent('Cascade Retail Partners · TY2025');
    // A client no run has reached has no year, so it cannot be answered for.
    expect(screen.getByRole('button', { name: 'Never Run' })).toBeDisabled();
  });

  it('a choice is the reader\u2019s reply: it re-asks the original, confirmed, for that client', async () => {
    asking();
    render(<ChatPanel scope={PORTFOLIO_SCOPE} />);
    await userEvent.type(screen.getByRole('textbox'), 'what is their trend?');
    await userEvent.click(screen.getByRole('button', { name: /send/i }));

    await userEvent.click(await screen.findByRole('button', { name: /Cascade Retail Partners/ }));

    await waitFor(() => expect(api.streamChat).toHaveBeenCalledTimes(2));
    const call = api.streamChat.mock.calls[1];
    expect(call[0]).toBe('what is their trend?');
    expect(scopeOf(call)).toMatchObject({ clientId: 2001, taxYear: 2025 });
    expect(call[5]).toEqual({ confirmed: true });
    // The history ends on the choice, so the NEXT "their" points at Cascade.
    expect(historyOf(call).at(-1)).toEqual({ role: 'user', text: 'Cascade Retail Partners' });
    // Shown once as the reply, and the original question not repeated.
    expect(screen.getAllByText('what is their trend?')).toHaveLength(1);
  });

  it('a follow-up after the choice stays on the chosen client', async () => {
    asking();
    render(<ChatPanel scope={PORTFOLIO_SCOPE} />);
    await userEvent.type(screen.getByRole('textbox'), 'what is their trend?');
    await userEvent.click(screen.getByRole('button', { name: /send/i }));
    await userEvent.click(await screen.findByRole('button', { name: /Cascade Retail Partners/ }));
    await waitFor(() => expect(api.streamChat).toHaveBeenCalledTimes(2));

    await userEvent.type(screen.getByRole('textbox'), 'and what else might they qualify for?');
    await userEvent.click(screen.getByRole('button', { name: /send/i }));
    await waitFor(() => expect(api.streamChat).toHaveBeenCalledTimes(3));
    expect(scopeOf(api.streamChat.mock.calls[2])).toMatchObject({ clientId: 2001, taxYear: 2025 });
    expect(api.streamChat.mock.calls[2][5]).toEqual({ confirmed: false });
  });

  it('a question can only be answered once', async () => {
    asking();
    render(<ChatPanel scope={PORTFOLIO_SCOPE} />);
    await userEvent.type(screen.getByRole('textbox'), 'what is their trend?');
    await userEvent.click(screen.getByRole('button', { name: /send/i }));
    await userEvent.click(await screen.findByRole('button', { name: /Cascade Retail Partners/ }));
    await waitFor(() => expect(screen.getByRole('button', { name: /Ironbridge Logistics/ })).toBeDisabled());
  });
});
