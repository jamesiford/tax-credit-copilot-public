import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchProgramDraft, saveProgramDraftDocuments } from '../../api.js';

/** How long after the last edit the draft saves itself. */
export const AUTOSAVE_MS = 1200;

/**
 * One draft, its local edits and its autosave.
 *
 * The documents being edited live here, apart from the server copy, so typing never re-renders from a response. A save names the
 * version it read; a 409 stops autosave and says so (`saveState: 'conflict'`) rather than overwriting somebody else's change.
 * Every action that reads the stored documents (validate, preview, review) flushes the pending edit first, because validating
 * what is on screen and not what is stored is how a review ends up about the wrong file.
 */
export default function useDraft(draftId) {
  const [draft, setDraft] = useState(null);
  const [docs, setDocsState] = useState(null);
  const [status, setStatus] = useState({ loading: Boolean(draftId), error: null });
  const [saveState, setSaveState] = useState('idle');
  const [savedAt, setSavedAt] = useState(null);
  const timer = useRef(null);
  const latest = useRef({ draft: null, docs: null, dirty: false });

  const adopt = useCallback((next) => {
    latest.current = { draft: next, docs: next.documents, dirty: false };
    setDraft(next);
    setDocsState(next.documents);
  }, []);

  const load = useCallback(async () => {
    if (!draftId) return;
    setStatus({ loading: true, error: null });
    try {
      const next = await fetchProgramDraft(draftId);
      if (!next?.draft_id) throw new Error('The server answered with nothing the page can show.');
      adopt(next);
      setStatus({ loading: false, error: null });
      setSaveState('idle');
    }
    catch (error) { setStatus({ loading: false, error }); }
  }, [draftId, adopt]);

  useEffect(() => { load(); return () => clearTimeout(timer.current); }, [load]);

  const save = useCallback(async () => {
    clearTimeout(timer.current);
    const { draft: current, docs: pending, dirty } = latest.current;
    if (!current || !dirty) return current;
    setSaveState('saving');
    try {
      const next = await saveProgramDraftDocuments(current.draft_id, { expectedVersion: current.version, pack: pending.pack, years: pending.years });
      latest.current = { draft: next, docs: pending, dirty: false };
      setDraft(next);
      setSaveState('saved');
      setSavedAt(new Date());
      return next;
    } catch (error) {
      setSaveState(error.status === 409 ? 'conflict' : 'error');
      throw error;
    }
  }, []);

  const setDocs = useCallback((pack, years) => {
    latest.current = { ...latest.current, docs: { pack, years }, dirty: true };
    setDocsState({ pack, years });
    setSaveState('dirty');
    clearTimeout(timer.current);
    timer.current = setTimeout(() => { save().catch(() => {}); }, AUTOSAVE_MS);
  }, [save]);

  /** Run an action against the stored draft after saving any pending edit, then re-read the draft (status, events, review). */
  const act = useCallback(async (call) => {
    await save();
    const response = await call(latest.current.draft.draft_id);
    // The full validation list comes only in the validate response; the stored copy is capped.
    const fresh = await fetchProgramDraft(latest.current.draft.draft_id);
    adopt(response?.documents && response.validation ? { ...fresh, validation: response.validation } : fresh);
    return response;
  }, [save, adopt]);

  return { draft, docs, status, saveState, savedAt, setDocs, save, act, reload: load, adopt };
}
