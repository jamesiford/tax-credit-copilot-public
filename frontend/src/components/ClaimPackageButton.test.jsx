/**
 * Download claim package: build server-side, stream through the API. [BLOB-4]
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ClaimPackageButton from './ClaimPackageButton.jsx';
import * as api from '../api.js';

beforeEach(() => {
  vi.spyOn(api, 'createClaimPackage').mockResolvedValue({ artifact_id: 'art-1', file_name: 'p.xlsx' });
  vi.spyOn(api, 'downloadArtifact').mockResolvedValue({ blob: new Blob(['x']), fileName: 'claim-package-1001-TY2024.xlsx' });
  globalThis.URL.createObjectURL = vi.fn(() => 'blob:local/1');
  globalThis.URL.revokeObjectURL = vi.fn();
});

afterEach(() => vi.restoreAllMocks());

describe('ClaimPackageButton', () => {
  it('builds the package for the scoped client-year, then downloads it through the API', async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    render(<ClaimPackageButton clientId={1001} taxYear={2024} />);

    await userEvent.click(screen.getByRole('button', { name: /Download claim package/ }));

    await waitFor(() => expect(api.downloadArtifact).toHaveBeenCalledWith(1001, 'art-1'));
    expect(api.createClaimPackage).toHaveBeenCalledWith(1001, 2024);
    expect(click).toHaveBeenCalled();
    expect(await screen.findByRole('status')).toHaveTextContent('claim-package-1001-TY2024.xlsx');
  });

  it('says "not calculated" rather than handing over an empty file', async () => {
    api.createClaimPackage.mockRejectedValue(new Error('package 409 · client 1001 has no completed calculation run'));
    render(<ClaimPackageButton clientId={1001} taxYear={2024} />);

    await userEvent.click(screen.getByRole('button', { name: /Download claim package/ }));

    expect(await screen.findByRole('status')).toHaveTextContent(/Not calculated yet/);
    expect(api.downloadArtifact).not.toHaveBeenCalled();
  });

  it('is disabled at portfolio scope or without a year', () => {
    const { rerender } = render(<ClaimPackageButton clientId="portfolio" taxYear={2024} />);
    expect(screen.getByRole('button', { name: /Download claim package/ })).toBeDisabled();
    rerender(<ClaimPackageButton clientId={1001} taxYear={null} />);
    expect(screen.getByRole('button', { name: /Download claim package/ })).toBeDisabled();
  });
});
