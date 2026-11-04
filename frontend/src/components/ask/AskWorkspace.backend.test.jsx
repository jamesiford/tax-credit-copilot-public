/**
 * The Ask workspace against the REAL backend stream shape. [CH-15d]
 *
 * `askBackendShape.json` is written by `backend/tests/test_chat_evidence.py`'s
 * builder and compared to it there, so it is what `/api/chat` emits, not a
 * fixture somebody invented. Here it travels as SSE text through the real
 * `streamChat` reader (only `fetch` is stubbed), so the parse, the router, the
 * validator and the pane are all the production ones.
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import shape from '../../lib/askBackendShape.json';
import { validateEvidence, tabCount } from '../../lib/evidence.js';
import AskWorkspace from './AskWorkspace.jsx';

// The backend's own framing: compact JSON, non-ASCII escaped (Python's json.dumps).
const frame = (event, data) => `event: ${event}\ndata: ${JSON.stringify(data).replace(/[\u007f-\uffff]/g, (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, '0')}`)}\n\n`;

const STREAM = [
  frame('plan', { intents: ['book', 'situation'], needs_client: [], capabilities: {} }),
  frame('status', { phase: 3, intent: 'book' }),
  frame('evidence', shape.book),
  frame('agent_start', { agent: 'ClientSituationAgent' }),
  frame('token', { agent: 'ClientSituationAgent', content: 'Call the first client.' }),
  frame('agent_end', { agent: 'ClientSituationAgent' }),
  frame('evidence', shape.situation),
  frame('done', {}),
].join('');

function sseResponse(text) {
  const bytes = new TextEncoder().encode(text);
  const body = new ReadableStream({ start(controller) { controller.enqueue(bytes); controller.close(); } });
  return { ok: true, status: 200, body };
}

beforeEach(() => {
  window.matchMedia = (query) => ({ matches: true, media: query, addEventListener() {}, removeEventListener() {} });
  vi.stubGlobal('fetch', vi.fn(async () => sseResponse(STREAM)));
});
afterEach(() => { vi.unstubAllGlobals(); document.documentElement.className = ''; });

describe('the backend evidence shape', () => {
  it('passes the contract with nothing dropped', () => {
    for (const item of Object.values(shape)) {
      const result = validateEvidence(item);
      expect(result.ok).toBe(true);
      expect(result.dropped).toBe(0);
    }
  });

  it('counts the first table, as the tab chip does', () => {
    expect(tabCount(validateEvidence(shape.book).item)).toBe(2);
    expect(tabCount(validateEvidence(shape.situation).item)).toBe(2);
  });
});

describe('the workspace reading a real stream', () => {
  async function open() {
    render(
      <AskWorkspace open onClose={() => {}} scope={{ clientId: 2001, year: 2023 }} onNavigate={() => {}} />,
    );
    await userEvent.type(screen.getByRole('textbox'), 'who should we call first?');
    await userEvent.click(screen.getByRole('button', { name: /^send/i }));
    return screen.findByRole('tablist', { name: 'Evidence' });
  }

  it('shows one tab per capability, in the order the backend sent them, with count chips', async () => {
    const tabs = within(await open()).getAllByRole('tab');
    expect(tabs.map((t) => t.textContent)).toEqual(['Who to call2', 'Situation2']);
  });

  it('renders the platform\u2019s own table, text and note verbatim', async () => {
    await open();
    const pane = screen.getByRole('region', { name: 'Evidence' });
    await userEvent.click(within(pane).getByRole('tab', { name: /Who to call/ }));
    const table = within(pane).getByRole('table');
    expect(within(table).getByText('Example Client B')).toBeInTheDocument();
    expect(within(table).getByText('-0.83')).toBeInTheDocument();
    expect(within(table).getByText('$40,495')).toBeInTheDocument();
    expect(within(table).getByText('\u2014')).toBeInTheDocument();
    expect(within(pane).getByText(/unverified assertion/)).toBeInTheDocument();
    expect(within(pane).getByText(shape.book.disclaimer)).toBeInTheDocument();
  });

  it('shows the situation heading as the title of the block it introduces, and its provenance', async () => {
    await open();
    const pane = screen.getByRole('region', { name: 'Evidence' });
    await userEvent.click(within(pane).getByRole('tab', { name: /Situation/ }));
    expect(within(pane).getByText('Example Client A')).toBeInTheDocument();
    expect(within(pane).getByText('ga_jtc/2023')).toBeInTheDocument();
    expect(within(pane).getAllByText('$31,185', { exact: false }).length).toBeGreaterThan(0);
  });

  it('leaves the narration where it was', async () => {
    await open();
    expect(await screen.findByText('Call the first client.')).toBeInTheDocument();
  });
});
