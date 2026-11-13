/*
 * Why: "Add a program" is a guided flow, not one giant form: basics, pack, years, preview, review, export. Each step is its own
 * page of the flow with its own validation beside it, the draft saves itself, and the history is always one scroll away. The
 * stepper never blocks (any available step can be opened) and a step that is not available says why.
 * Never: let a step suggest the statute is verified. The notice at the top stays on every step.
 */
import { useState } from 'react';
import { createProgramDraft } from '../../api.js';
import { stepStates } from '../../lib/programs.js';
import PageHeader from '../PageHeader.jsx';
import EmptyState from '../ui/EmptyState.jsx';
import Skeleton from '../ui/Skeleton.jsx';
import Stepper from '../ui/Stepper.jsx';
import { DraftStatusBadge } from './Badges.jsx';
import DraftHistory from './DraftHistory.jsx';
import StepBasics from './StepBasics.jsx';
import StepExport from './StepExport.jsx';
import StepPack from './StepPack.jsx';
import StepPreview from './StepPreview.jsx';
import StepReview from './StepReview.jsx';
import StepYears from './StepYears.jsx';
import UnverifiedNotice from './UnverifiedNotice.jsx';
import useDraft from './useDraft.js';
import Callout from '../ui/Callout.jsx';

const SAVE_TEXT = { idle: '', dirty: 'Unsaved changes', saving: 'Saving\u2026', saved: 'Saved', conflict: 'Not saved: changed elsewhere', error: 'Not saved' };

function SaveState({ saveState, savedAt, onReload }) {
  const time = saveState === 'saved' && savedAt ? ` ${savedAt.toTimeString().slice(0, 5)}` : '';
  return (
    <span className="prog-savestate" role="status" aria-live="polite">
      {SAVE_TEXT[saveState]}{time}
      {saveState === 'conflict' ? <> <button type="button" className="tcc-link" onClick={onReload}>Reload the latest</button></> : null}
    </span>
  );
}

export default function AddProgramWorkflow({ draftId, catalog, onCreated, onExit }) {
  const state = useDraft(draftId);
  const [step, setStep] = useState(draftId ? 'pack' : 'basics');
  const { draft, docs } = state;
  const back = { label: 'All programs', onClick: onExit };

  if (draftId && state.status.loading) return <><PageHeader eyebrow="Program manager" title="Add a program" back={back} /><Skeleton lines={5} label="Opening the draft" /></>;
  if (draftId && state.status.error) {
    return (
      <><PageHeader eyebrow="Program manager" title="Add a program" back={back} />
        <EmptyState title={state.status.error.status === 404 ? 'No such draft' : 'The draft could not be opened'}>
          {state.status.error.reason || state.status.error.message} Nothing was changed.
        </EmptyState></>
    );
  }
  const create = async (body) => { const made = await createProgramDraft(body); onCreated(made.draft_id); };
  const stale = Boolean(draft?.validation) && state.saveState === 'dirty';
  const steps = stepStates(draft, step);
  const current = steps.find((s) => s.id === step)?.status === 'disabled' ? 'basics' : step;
  const shared = { draft, docs, setDocs: state.setDocs, act: state.act, stale };

  return (
    <>
      <PageHeader
        eyebrow="Program manager" title={draft ? draft.name : 'Add a program'} back={back}
        sub={draft ? `${draft.proposed_code} \u00b7 version ${draft.version}` : 'A guided flow: a draft, validated and reviewed, then exported for a person to commit'}
        actions={draft ? <DraftStatusBadge status={draft.status} /> : null}
      />
      <UnverifiedNotice title="Not verified, and not live" />
      <Stepper steps={steps} label="Add a program" onSelect={setStep} />
      {draft ? <div className="prog-actions"><SaveState saveState={state.saveState} savedAt={state.savedAt} onReload={state.reload} /></div> : null}
      {state.saveState === 'conflict' || state.saveState === 'error' ? (
        <Callout tone="partial" title="Your last change was not saved"><p>
          {state.saveState === 'conflict' ? 'Someone else changed this draft. Reload the latest version, then make the change again.' : 'The save failed. Nothing was lost on this page: try again.'}
        </p></Callout>
      ) : null}
      <div className="prog-stack" aria-live="polite">
        {current === 'basics' && <StepBasics draft={draft} catalog={catalog} onCreate={create} />}
        {draft && current === 'pack' && <StepPack {...shared} />}
        {draft && current === 'years' && <StepYears {...shared} />}
        {draft && current === 'preview' && <StepPreview draft={draft} act={state.act} />}
        {draft && current === 'review' && <StepReview draft={draft} act={state.act} stale={stale} />}
        {draft && current === 'export' && <StepExport draft={draft} act={state.act} />}
        {draft ? <DraftHistory events={draft.events} /> : null}
      </div>
    </>
  );
}
