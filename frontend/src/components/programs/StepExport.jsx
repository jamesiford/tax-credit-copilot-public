/*
 * Why: step 6 hands the reviewed bundle to a human. The download is deterministic (the same draft gives the same bytes and hash),
 * the manifest lists every file, and the next steps are the commit checklist: who must verify the statute, where the files go,
 * the tests and changelog line, and that nothing is calculable until the deploy.
 * Never: say the program is now live, or that exporting verified anything.
 */
import { useEffect, useState } from 'react';
import { exportProgramDraft, fetchProgramDraftManifest } from '../../api.js';
import { NEXT_STEPS } from '../../lib/programs.js';
import Button from '../ui/Button.jsx';
import Callout from '../ui/Callout.jsx';
import Card from '../ui/Card.jsx';
import Skeleton from '../ui/Skeleton.jsx';

function save(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url; link.download = filename; link.click();
  URL.revokeObjectURL(url);
}

export default function StepExport({ draft, act }) {
  const [manifest, setManifest] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [exported, setExported] = useState(null);
  useEffect(() => {
    let cancelled = false;
    fetchProgramDraftManifest(draft.draft_id).then((m) => { if (!cancelled) setManifest(m); }).catch((e) => { if (!cancelled) setError(e); });
    return () => { cancelled = true; };
  }, [draft.draft_id, draft.status]);
  const download = async () => {
    setBusy(true); setError(null);
    try {
      const out = await act(() => exportProgramDraft(draft.draft_id));
      save(out.blob, out.filename); setExported(out.sha256);
    } catch (reason) { setError(reason); } finally { setBusy(false); }
  };
  return (
    <div className="prog-grid-2">
      <Card title="Export the reviewed bundle" subtitle="A zip for a person to commit; the app never writes into the source tree">
        <Callout tone="partial" title="Exporting activates nothing">
          <p>The bundle is a proposal. The program becomes calculable only when a person commits the files and deploys, for its authored years only.</p>
        </Callout>
        {error ? <Callout tone="partial" title="The bundle could not be exported"><p>{error.reason || error.message}</p></Callout> : null}
        <div className="prog-actions">
          <Button variant="primary" onClick={download} loading={busy} disabled={!draft.allowed_actions.includes('export')}>Download the bundle</Button>
          {exported || draft.export.bundle_sha256 ? <span className="small">SHA-256 <code>{exported || draft.export.bundle_sha256}</code></span> : null}
        </div>
        <h4>Next steps for a person</h4>
        <ol>{NEXT_STEPS.map((s) => <li key={s}>{s}</li>)}</ol>
      </Card>
      <Card title="What is in the bundle" subtitle={manifest ? `${manifest.files.length} files, ${manifest.bundle_bytes} bytes` : undefined}>
        {!manifest && !error ? <Skeleton lines={4} label="Reading the manifest" /> : null}
        {manifest ? (
          <table className="tbl-compact" aria-label="Bundle files">
            <thead><tr><th>File</th><th>SHA-256</th></tr></thead>
            <tbody>{manifest.files.map((f) => <tr key={f.path}><td><code>{f.path}</code></td><td className="small"><code>{f.sha256.slice(0, 12)}</code></td></tr>)}</tbody>
          </table>
        ) : null}
      </Card>
    </div>
  );
}
