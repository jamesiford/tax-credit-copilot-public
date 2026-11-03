import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { CONFIRMATION_EVIDENCE } from '../../lib/askFixtures.js';
import { validateEvidence } from '../../lib/evidence.js';
import ConfirmCard from './ConfirmCard.jsx';

const item = validateEvidence(CONFIRMATION_EVIDENCE).item;
const NOW = Date.parse('2030-01-01T00:00:00Z');

describe('ConfirmCard', () => {
  it('previews what would be recorded, in the platform\u2019s own words', () => {
    render(<ConfirmCard item={item} onConfirm={() => {}} onCancel={() => {}} now={NOW} />);
    expect(screen.getByText('Count E00200 at GA_MAC_OPS for 2025-02.')).toBeInTheDocument();
    expect(screen.getByRole('table', { name: 'What would be recorded' })).toHaveTextContent('2025-02');
    expect(screen.getByText('Expires at 2099-01-01T00:00:00Z.')).toBeInTheDocument();
  });

  it('confirms only on a click, with the item, and cancels the same way', async () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(<ConfirmCard item={item} onConfirm={onConfirm} onCancel={onCancel} now={NOW} />);
    expect(onConfirm).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    expect(onConfirm).toHaveBeenCalledWith(item);
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onCancel).toHaveBeenCalledWith(item);
  });

  it('cannot confirm once it has expired, and says so', () => {
    render(<ConfirmCard item={item} onConfirm={() => {}} now={Date.parse('2100-01-01T00:00:00Z')} />);
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeDisabled();
    expect(screen.getByText(/Expired at 2099-01-01T00:00:00Z/)).toBeInTheDocument();
  });

  it('is inert without a handler and says so instead of looking connected', () => {
    render(<ConfirmCard item={item} now={NOW} />);
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeDisabled();
    expect(screen.getByText(/not connected in this build/)).toBeInTheDocument();
    // Cancel is always safe.
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeEnabled();
  });

  it('is amber, not red and not the selection blue: nothing has failed', () => {
    const { container } = render(<ConfirmCard item={item} onConfirm={() => {}} now={NOW} />);
    expect(container.querySelector('.ui-card-verdict-partial')).not.toBeNull();
  });
});
