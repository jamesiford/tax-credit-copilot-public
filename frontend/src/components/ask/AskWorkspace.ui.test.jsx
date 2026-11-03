/**
 * The workspace as a place: it opens and closes, traps focus, says what it is
 * about, names its plan, shows the platform's evidence verbatim, and falls back
 * to deep links when the platform sends none.
 *
 * (The conversation rules the retired ChatPanel pinned live in
 * AskWorkspace.test.jsx, unchanged.)
 */
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../../api.js';
import {
  ELIGIBILITY_EVIDENCE, TREND_EVIDENCE, CONFIRMATION_EVIDENCE, PLAN_EVENT,
} from '../../lib/askFixtures.js';
import AskWorkspace from './AskWorkspace.jsx';

const SCOPE = { clientId: 2001, year: 2023, jurisdiction: 'GA' };

function Harness({ scope = SCOPE, onNavigate = () => {}, startOpen = false, ...rest }) {
  const [open, setOpen] = useState(startOpen);
  return (
    <>
      <button id="ask-launcher" type="button" onClick={() => setOpen(true)}>Launch</button>
      <button type="button">Behind the workspace</button>
      <AskWorkspace
        open={open}
        onClose={() => setOpen(false)}
        scope={scope}
        nameFor={(id) => (String(id) === '2001' ? 'Example Client A' : undefined)}
        onNavigate={onNavigate}
        pagePrompt="Summarize this page."
        {...rest}
      />
    </>
  );
}

const emit = (events) => api.streamChat.mockImplementation(async (_m, onEvent) => {
  for (const ev of events) onEvent(ev);
});

const PLAIN = [
  { event: 'plan', data: PLAN_EVENT },
  { event: 'agent_start', data: { agent: 'CreditRulesAgent' } },
  { event: 'token', data: { agent: 'CreditRulesAgent', content: 'Three locations are low.' } },
  { event: 'agent_end', data: { agent: 'CreditRulesAgent' } },
  { event: 'done', data: {} },
];

// jsdom has no layout: say which one this test is in. The setup file defaults to narrow.
const setViewport = (wide) => {
  window.matchMedia = (query) => ({
    matches: wide, media: query, addEventListener() {}, removeEventListener() {},
  });
};

beforeEach(() => { setViewport(true); vi.spyOn(api, 'streamChat'); emit(PLAIN); });
afterEach(() => { vi.restoreAllMocks(); document.documentElement.className = ''; });

async function ask(text = 'how are we doing?') {
  await userEvent.type(screen.getByRole('textbox'), text);
  await userEvent.click(screen.getByRole('button', { name: /^send/i }));
}

describe('opening and closing', () => {
  it('draws nothing while closed, and a dialog named for itself when open', async () => {
    render(<Harness />);
    expect(screen.queryByRole('dialog')).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Launch' }));
    expect(screen.getByRole('dialog', { name: /Ask Copilot/ })).toHaveAttribute('aria-modal', 'true');
  });

  it('puts focus in the composer, and Tab never leaves the dialog', async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole('button', { name: 'Launch' }));
    const dialog = screen.getByRole('dialog');
    expect(screen.getByRole('textbox')).toHaveFocus();

    for (let i = 0; i < 25; i += 1) {
      await userEvent.tab();
      expect(dialog.contains(document.activeElement)).toBe(true);
    }
    for (let i = 0; i < 25; i += 1) {
      await userEvent.tab({ shift: true });
      expect(dialog.contains(document.activeElement)).toBe(true);
    }
    expect(screen.getByRole('button', { name: 'Behind the workspace' })).not.toHaveFocus();
  });

  it('Escape closes it and focus goes back to what opened it', async () => {
    render(<Harness />);
    const launcher = screen.getByRole('button', { name: 'Launch' });
    await userEvent.click(launcher);
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
    await waitFor(() => expect(launcher).toHaveFocus());
  });

  it('the close button closes it too', async () => {
    render(<Harness startOpen />);
    await userEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('locks the page behind it while open, and releases it', async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole('button', { name: 'Launch' }));
    expect(document.documentElement).toHaveClass('ask-open');
    await userEvent.keyboard('{Escape}');
    expect(document.documentElement).not.toHaveClass('ask-open');
  });

  it('falls back to the launcher when what opened it has left the page', async () => {
    function Gone() {
      const [open, setOpen] = useState(false);
      return (
        <>
          {open ? null : <button id="ask-launcher" type="button" onClick={() => setOpen(true)}>Launch</button>}
          <AskWorkspace open={open} onClose={() => setOpen(false)} scope={SCOPE} />
        </>
      );
    }
    render(<Gone />);
    await userEvent.click(screen.getByRole('button', { name: 'Launch' }));
    await userEvent.keyboard('{Escape}');
    await waitFor(() => expect(screen.getByRole('button', { name: 'Launch' })).toHaveFocus());
  });

  it('keeps the conversation when it is closed and opened again', async () => {
    render(<Harness startOpen />);
    await ask('first question');
    await screen.findByText('Three locations are low.');
    await userEvent.keyboard('{Escape}');
    await userEvent.click(screen.getByRole('button', { name: 'Launch' }));
    expect(screen.getByText('first question')).toBeInTheDocument();
    expect(screen.getByText('Three locations are low.')).toBeInTheDocument();
  });
});

describe('what the conversation is about', () => {
  it('states client, tax year and method in the header', () => {
    render(<Harness startOpen />);
    const about = within(screen.getByRole('dialog')).getByText('Client').closest('dl');
    expect(about).toHaveTextContent('Example Client A');
    expect(about).toHaveTextContent('TY2023');
    expect(about).toHaveTextContent('Min-Max');
  });

  it('says it is about every client at portfolio scope, and offers no year it does not have', () => {
    render(<Harness startOpen scope={{ clientId: 'portfolio' }} />);
    const about = screen.getByText('Client').closest('dl');
    expect(about).toHaveTextContent('All clients');
    expect(about).not.toHaveTextContent('Tax year');
  });

  it('follows the client an ask pinned, not the shell', async () => {
    render(<Harness startOpen scope={{ clientId: 'portfolio' }} queuedPrompt="Brief me" queuedScope={{ clientId: 2001, taxYear: 2025 }} />);
    await waitFor(() => expect(api.streamChat).toHaveBeenCalled());
    const about = screen.getByText('Client').closest('dl');
    expect(about).toHaveTextContent('Example Client A');
    expect(about).toHaveTextContent('TY2025');
  });

  it('"Ask about this page" asks the page prompt', async () => {
    render(<Harness startOpen />);
    await userEvent.click(screen.getByRole('button', { name: 'Ask about this page' }));
    await waitFor(() => expect(api.streamChat).toHaveBeenCalled());
    expect(api.streamChat.mock.calls[0][0]).toBe('Summarize this page.');
  });
});

describe('the plan strip', () => {
  it('names what the answer used, from the plan event', async () => {
    render(<Harness startOpen />);
    await ask();
    expect(await screen.findByLabelText('Plan')).toHaveTextContent('Using: Eligibility · Trend');
  });

  it('says which capabilities need a client', async () => {
    emit([{ event: 'plan', data: { intents: ['book'], needs_client: ['trend'], capabilities: {} } }, { event: 'done', data: {} }]);
    render(<Harness startOpen scope={{ clientId: 'portfolio' }} />);
    await ask();
    expect(await screen.findByLabelText('Plan')).toHaveTextContent('Needs a client selected: Trend');
  });

  it('shows the agent as a pill, not a coloured badge', async () => {
    render(<Harness startOpen />);
    await ask();
    const pill = await screen.findByText('Credit Rules');
    expect(pill.closest('.ui-pill')).not.toBeNull();
  });
});

describe('clarification', () => {
  it('numbers the choices, and a screen reader hears only the name', async () => {
    emit([
      { event: 'agent_start', data: { agent: 'OrchestratorAgent' } },
      { event: 'token', data: { agent: 'OrchestratorAgent', content: 'Which client?' } },
      { event: 'clarify', data: { message: 'q', reason: 'r', choices: [{ client_id: 1, name: 'First Co', tax_year: 2023 }, { client_id: 2, name: 'Second Co', tax_year: 2022 }] } },
      { event: 'done', data: {} },
    ]);
    render(<Harness startOpen scope={{ clientId: 'portfolio' }} />);
    await ask('q');
    const group = await screen.findByRole('group', { name: 'Which client?' });
    expect(group).toHaveTextContent('1)First Co');
    expect(group).toHaveTextContent('2)Second Co');
    expect(within(group).getByRole('button', { name: /^First Co/ })).toBeInTheDocument();
  });
});

describe('the composer', () => {
  it('Need clarification? puts a question in the composer without sending it', async () => {
    render(<Harness startOpen />);
    await userEvent.click(screen.getByRole('button', { name: 'Need clarification?' }));
    expect(screen.getByRole('textbox').value).toMatch(/which tools did you use/);
    expect(api.streamChat).not.toHaveBeenCalled();
  });

  it('offers the suggested prompts before anything is said, and sends one on click', async () => {
    render(<Harness startOpen />);
    await userEvent.click(screen.getByRole('button', { name: /Walk me through how you got that number/ }));
    await waitFor(() => expect(api.streamChat).toHaveBeenCalled());
  });

  it('can be driven entirely from the keyboard', async () => {
    render(<Harness />);
    screen.getByRole('button', { name: 'Launch' }).focus();
    await userEvent.keyboard('{Enter}');
    await userEvent.keyboard('hello there{Enter}');
    await waitFor(() => expect(api.streamChat).toHaveBeenCalled());
    expect(api.streamChat.mock.calls[0][0]).toBe('hello there');
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});

describe('when the assistant is unavailable', () => {
  it('says so in the product\u2019s words, says nothing was changed, and offers a retry', async () => {
    api.streamChat.mockRejectedValueOnce(new Error('chat 500'));
    render(<Harness startOpen />);
    await ask();
    expect(await screen.findByText('The assistant is unavailable')).toBeInTheDocument();
    expect(screen.getByText(/still shows the engine/)).toBeInTheDocument();
    expect(screen.getByText(/chat 500/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await screen.findByText('Three locations are low.');
    expect(screen.queryByText('The assistant is unavailable')).toBeNull();
  });
});

describe('the evidence pane', () => {
  const WITH_EVIDENCE = [
    ...PLAIN.slice(0, 4),
    { event: 'evidence', data: ELIGIBILITY_EVIDENCE },
    { event: 'evidence', data: TREND_EVIDENCE },
    { event: 'done', data: {} },
  ];

  it('renders the platform\u2019s items as tabs with count chips', async () => {
    emit(WITH_EVIDENCE);
    render(<Harness startOpen />);
    await ask();
    const tabs = within(await screen.findByRole('tablist', { name: 'Evidence' })).getAllByRole('tab');
    expect(tabs.map((t) => t.textContent)).toEqual(['Eligibility3', 'Trend3']);
  });

  it('shows tiles, a table, a derivation, provenance and the disclaimer', async () => {
    emit(WITH_EVIDENCE);
    render(<Harness startOpen />);
    await ask();
    const pane = await screen.findByRole('region', { name: 'Evidence' });
    // The newest item is the one showing; go back to the first.
    await userEvent.click(within(pane).getByRole('tab', { name: /Eligibility/ }));
    expect(within(pane).getByRole('group', { name: 'Headline' })).toHaveTextContent('539');
    expect(within(pane).getByRole('table', { name: 'Locations' })).toBeInTheDocument();
    expect(within(pane).getByText('Why this reading')).toBeInTheDocument();
    expect(within(pane).getByText('ga_jtc/2023')).toBeInTheDocument();
    expect(within(pane).getByText(ELIGIBILITY_EVIDENCE.provenance.trail_hash)).toBeInTheDocument();
    expect(within(pane).getByText(ELIGIBILITY_EVIDENCE.disclaimer)).toBeInTheDocument();
  });

  it('NUMBERS VERBATIM: every figure in the pane is a string the platform sent', async () => {
    emit(WITH_EVIDENCE);
    render(<Harness startOpen />);
    await ask();
    const pane = await screen.findByRole('region', { name: 'Evidence' });
    for (const label of ['Eligibility', 'Trend']) {
      await userEvent.click(within(pane).getByRole('tab', { name: new RegExp(label) }));
      const sent = JSON.stringify(label === 'Eligibility' ? ELIGIBILITY_EVIDENCE : TREND_EVIDENCE);
      // Scan text node by node: textContent glues a tab's count chip to the next
      // figure ("3" + "539"), which is not a figure anyone wrote.
      const figures = [];
      const walker = document.createTreeWalker(pane, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) figures.push(...(walker.currentNode.textContent.match(/-?\$?\d[\d,]*(?:\.\d+)?/g) || []));
      expect(figures.length).toBeGreaterThan(0);
      for (const figure of figures) {
        // A figure the pane shows must be one the platform wrote. (Digits in
        // the item's own prose, like "TY2021", are inside strings it wrote.)
        expect(sent).toContain(figure);
      }
    }
  });

  it('keeps trailing zeros and signs exactly as sent', async () => {
    emit([{
      event: 'evidence',
      data: { tool: 'x', title: 'Exact', blocks: [{ kind: 'table', columns: ['v'], rows: [['410.10'], ['-0.50']] }] },
    }, { event: 'done', data: {} }]);
    render(<Harness startOpen />);
    await ask();
    expect(await screen.findByText('410.10')).toBeInTheDocument();
    expect(screen.getByText('-0.50')).toBeInTheDocument();
  });

  it('ignores an event it does not know and an evidence payload that breaks the contract', async () => {
    emit([
      ...PLAIN.slice(0, 4),
      { event: 'weather', data: { sunny: true } },
      { event: 'evidence', data: { tool: 'x', blocks: [{ kind: 'hologram' }] } },
      { event: 'evidence', data: 'not an object' },
      { event: 'done', data: {} },
    ]);
    render(<Harness startOpen />);
    await ask();
    await screen.findByText('Three locations are low.');
    expect(screen.queryByRole('tablist', { name: 'Evidence' })).toBeNull();
    expect(screen.getByText("The engine\u0027s figures are on the page")).toBeInTheDocument();
  });

  it('says when a block was dropped for not fitting the contract', async () => {
    emit([{
      event: 'evidence',
      data: { tool: 'x', blocks: [{ kind: 'text', text: 'kept' }, { kind: 'hologram' }] },
    }, { event: 'done', data: {} }]);
    render(<Harness startOpen />);
    await ask();
    expect(await screen.findByText(/1 block from the platform did not fit/)).toBeInTheDocument();
  });

  it('without evidence, offers a Show on page chip per capability, and navigates', async () => {
    const onNavigate = vi.fn();
    render(<Harness startOpen onNavigate={onNavigate} />);
    await ask();
    const chips = await screen.findByRole('list', { name: 'Show on page' });
    const link = within(chips).getByRole('link', { name: /Show Eligibility on page/ });
    expect(link).toHaveAttribute('href', '/c/2001/eligibility?year=2023');
    await userEvent.click(link);
    expect(onNavigate).toHaveBeenCalledWith('/c/2001/eligibility?year=2023');
  });

  it('a chip that needs a client says so rather than vanishing', async () => {
    render(<Harness startOpen scope={{ clientId: 'portfolio' }} />);
    await ask();
    const chip = await screen.findByText(/Show Eligibility on page/);
    expect(chip.closest('[aria-disabled="true"]')).not.toBeNull();
    expect(chip).toHaveTextContent('Pick a client first');
  });

  it('a new chat clears the evidence', async () => {
    emit(WITH_EVIDENCE);
    render(<Harness startOpen />);
    await ask();
    await screen.findByRole('tablist', { name: 'Evidence' });
    await userEvent.click(screen.getByRole('button', { name: /new chat/i }));
    expect(screen.queryByRole('tablist', { name: 'Evidence' })).toBeNull();
  });

  it('a confirmation renders its preview and stays inert without a handler', async () => {
    emit([{ event: 'evidence', data: CONFIRMATION_EVIDENCE }, { event: 'done', data: {} }]);
    render(<Harness startOpen />);
    await ask();
    const card = await screen.findByRole('article', { name: 'Confirm a decision' });
    expect(within(card).getByText('GA_MAC_OPS')).toBeInTheDocument();
    expect(within(card).getByRole('button', { name: 'Confirm' })).toBeDisabled();
    expect(card).toHaveTextContent('not connected in this build');
  });
});

describe('the narrow layout', () => {
  const narrow = () => setViewport(false);

  it('stacks the evidence behind a tab that carries its count', async () => {
    narrow();
    emit([...PLAIN.slice(0, 4), { event: 'evidence', data: ELIGIBILITY_EVIDENCE }, { event: 'done', data: {} }]);
    render(<Harness startOpen />);
    const tabs = screen.getByRole('tablist', { name: 'Workspace' });
    expect(within(tabs).getByRole('tab', { name: /Conversation/ })).toHaveAttribute('aria-selected', 'true');
    // Only one pane at a time.
    expect(screen.queryByRole('region', { name: 'Evidence' })).toBeNull();

    await ask();
    await waitFor(() => expect(within(tabs).getByRole('tab', { name: /Evidence/ })).toHaveTextContent('1'));
    await userEvent.click(within(tabs).getByRole('tab', { name: /Evidence/ }));
    expect(screen.getByRole('region', { name: 'Evidence' })).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).toBeNull();
  });

  it('the wide layout shows both and has no workspace tabs', () => {
    render(<Harness startOpen />);
    expect(screen.queryByRole('tablist', { name: 'Workspace' })).toBeNull();
    expect(screen.getByRole('region', { name: 'Conversation' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Evidence' })).toBeInTheDocument();
  });
});

describe('dev fixture mode', () => {
  it('replays the fixture stream, evidence included, with no backend', async () => {
    window.history.pushState({}, '', '/?askFixture=1');
    try {
      render(<Harness startOpen />);
      await ask('how are we doing?');
      expect(api.streamChat).not.toHaveBeenCalled();
      expect(await screen.findByRole('tablist', { name: 'Evidence' })).toBeInTheDocument();
    } finally {
      window.history.pushState({}, '', '/');
    }
  });
});
