import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import InsightBar, { provenanceLine } from './InsightBar.jsx';
import * as api from '../api.js';

/**
 * The line that replaced the page-opening banners (29 Sep).
 *
 * Three promises: the notes are always in the page (a disclosure is never one
 * render from gone), the Copilot summary costs nothing until it is opened, and
 * the summary says which of its figures the page's data does not hold.
 */

function stream(events) {
  return vi.spyOn(api, 'streamPageSummary').mockImplementation(async (_req, onEvent) => {
    for (const [event, data] of events) onEvent({ event, data });
  });
}

beforeEach(() => { vi.restoreAllMocks(); });
afterEach(() => { vi.restoreAllMocks(); });

describe('the caption and its notes', () => {
  it('shows the caption and keeps every note in the page behind the (i)', () => {
    render(<InsightBar caption="6 locations · 4 qualify" notes={['Base year is inferred.', null, 'Run abc']} />);
    expect(screen.getByText('6 locations · 4 qualify')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Notes about these figures' })).toBeInTheDocument();
    expect(screen.getByText('Base year is inferred.')).toBeInTheDocument();
    expect(screen.getByText('Run abc')).toBeInTheDocument();
  });

  it('pins the notes open on click', async () => {
    render(<InsightBar notes={['A note']} />);
    const button = screen.getByRole('button', { name: 'Notes about these figures' });
    await userEvent.click(button);
    expect(button).toHaveAttribute('aria-expanded', 'true');
  });

  it('offers no Copilot without a scope to summarise', () => {
    render(<InsightBar caption="x" />);
    expect(screen.queryByRole('button', { name: /Copilot summary/ })).not.toBeInTheDocument();
  });
});

describe('the Copilot summary', () => {
  const request = { page: 'client', clientId: 2001, state: 'GA', method: 'min_max' };

  it('costs nothing until it is opened', async () => {
    const spy = stream([]);
    render(<InsightBar caption="x" request={request} />);
    expect(spy).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: /Copilot summary/ }));
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1));
    expect(spy.mock.calls[0][0]).toEqual(request);
  });

  it('streams the headlines and says every figure checked out', async () => {
    stream([
      ['brief', { headline: 'h' }],
      ['token', { content: '- **GA_GA-016** is behind pace' }],
      ['token', { content: ' in TY2026.' }],
      ['check', { unsupported: [] }],
    ]);
    render(<InsightBar request={request} />);
    await userEvent.click(screen.getByRole('button', { name: /Copilot summary/ }));
    expect(await screen.findByText(/is behind pace in TY2026/)).toBeInTheDocument();
    expect(screen.getByText('GA_GA-016').tagName).toBe('STRONG');
    expect(await screen.findByText(/Every figure checked against this page/)).toBeInTheDocument();
    expect(screen.getByText(/The figures are computed; the wording is not/)).toBeInTheDocument();
  });

  it('names a figure the data does not hold rather than letting it pass', async () => {
    stream([['token', { content: 'Worth $40,000.' }], ['check', { unsupported: ['$40,000'] }]]);
    render(<InsightBar request={request} />);
    await userEvent.click(screen.getByRole('button', { name: /Copilot summary/ }));
    expect(await screen.findByText(/\$40,000 does not appear in this page.s data/)).toBeInTheDocument();
  });

  it('without Copilot, says the computed facts and that they are', async () => {
    stream([['fallback', { facts: ['6 locations.', '4 qualify.'], note: 'Copilot is not connected; these are the computed facts.' }]]);
    render(<InsightBar request={request} />);
    await userEvent.click(screen.getByRole('button', { name: /Copilot summary/ }));
    expect(await screen.findByText('4 qualify.')).toBeInTheDocument();
    expect(screen.getByText(/Copilot is not connected/)).toBeInTheDocument();
  });

  it('collapsing and reopening does not pay for a second narration', async () => {
    const spy = stream([['token', { content: 'Once.' }], ['check', { unsupported: [] }]]);
    render(<InsightBar request={request} />);
    const toggle = screen.getByRole('button', { name: /Copilot summary/ });
    await userEvent.click(toggle);
    await screen.findByText('Once.');
    await userEvent.click(toggle);
    await userEvent.click(toggle);
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('says so when the summary could not be written', async () => {
    stream([['error', { detail: 'a unit summary needs worksite_id' }]]);
    render(<InsightBar request={request} />);
    await userEvent.click(screen.getByRole('button', { name: /Copilot summary/ }));
    expect(await screen.findByText('a unit summary needs worksite_id')).toBeInTheDocument();
  });
});

describe('the run behind the figures', () => {
  it('names it in one line', () => {
    expect(provenanceLine({
      run_id: '1ef66984739b4a', produced_at: '2026-09-26T01:24:40', rule_pack_version: 'rules/ga_jtc/2025.json', code_commit: '18fafd4aa',
    })).toBe('Run 1ef66984739b · produced 2026-09-26T01:24:40 · statute rules/ga_jtc/2025.json · code 18fafd4');
    expect(provenanceLine(null)).toBeNull();
  });
});
