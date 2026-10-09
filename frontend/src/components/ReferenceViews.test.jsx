/**
 * Every page heading must match the nav label that opened it.
 *
 * These views are one-line JSX, so a bad edit can turn a heading into loose
 * text and still compile with only a warning. The suite used to stay green
 * while Back-test rendered a sentence fragment where its header belonged.
 */
import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { CompareView, OneZeroView } from './ReferenceViews.jsx';
import * as api from '../api.js';
import { PORTFOLIO } from '../lib/scopeDimension.js';

describe('page headings follow the navigation labels', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchWorkspaceComparison').mockResolvedValue({
      status: 'not_supplied', message: 'No Access package yet.', required_stages: ['eligibility'],
    });
  });
  afterEach(() => vi.restoreAllMocks());

  it('titles the Access reconciliation "Back-test"', async () => {
    render(<CompareView openEmployee={() => {}} />);
    expect(screen.getByRole('heading', { name: 'Back-test' })).toBeInTheDocument();
    expect(screen.getByText(/Stage-by-stage reconciliation against the partner’s Access output/)).toBeInTheDocument();
    expect(await screen.findByText('Access outputs not supplied')).toBeInTheDocument();
  });

  it('titles the one/zero matrix "Monthly employment", and explains itself at portfolio scope', () => {
    render(<OneZeroView openEmployee={() => {}} scope={{ clientId: PORTFOLIO, year: 2023 }} />);
    expect(screen.getByRole('heading', { name: 'Monthly employment' })).toBeInTheDocument();
    expect(screen.getByText(/Monthly employment allocates one client’s employees/)).toBeInTheDocument();
  });
});
