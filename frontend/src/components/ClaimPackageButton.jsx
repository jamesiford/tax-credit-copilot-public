import { useState } from 'react';
import { Download } from 'lucide-react';
import { createClaimPackage, downloadArtifact } from '../api.js';
import { PORTFOLIO } from '../lib/scopeDimension.js';

/**
 * Download claim package. [BLOB-4]
 *
 * The workbook is built by the API from what the run already wrote, stored,
 * and then streamed back through the API: the browser never holds a storage
 * URL. Unit grain only — there is nothing in it about an individual employee.
 */
export default function ClaimPackageButton({ clientId, taxYear }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);

  const unavailable = clientId == null || clientId === PORTFOLIO || taxYear == null;

  const onClick = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const artifact = await createClaimPackage(clientId, taxYear);
      const { blob, fileName } = await downloadArtifact(clientId, artifact.artifact_id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = fileName;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setMessage(`Downloaded ${fileName}`);
    } catch (reason) {
      const text = String(reason?.message || reason);
      setMessage(text.startsWith('package 409')
        ? 'Not calculated yet: run a calculation for this client before packaging it.'
        : `Could not build the claim package (${text}).`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="tcc-claim-package">
      <button
        type="button"
        className="btn btn-secondary"
        onClick={onClick}
        disabled={unavailable || busy}
        title={unavailable ? 'Select a client and a tax year' : `Claim package for TY${taxYear}`}
      >
        <Download size={14} aria-hidden="true" />
        {busy ? ' Building…' : ' Download claim package'}
      </button>
      {message ? <span className="muted u-ml-1" role="status">{message}</span> : null}
    </div>
  );
}
