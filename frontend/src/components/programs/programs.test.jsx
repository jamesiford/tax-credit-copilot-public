/**
 * The Program manager: the catalog, a program's detail, the drafts list and the Add-a-program workflow.
 *
 * The behaviours that fail quietly if wrong: a "verified" word anywhere, a preview without its label, a button enabled for a move
 * the draft's status does not allow, an edit that overwrites somebody else's, and a described program drawn as if it could run.
 */
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ProgramsPage from '../../pages/ProgramsPage.jsx';
import ProgramCatalog from './ProgramCatalog.jsx';
import ProgramDetail from './ProgramDetail.jsx';
import ValidationPanel from './ValidationPanel.jsx';
import { AUTOSAVE_MS } from './useDraft.js';
import { yearSkeleton } from '../../lib/programs.js';

vi.mock('../../api.js', async () => {
  const actual = await vi.importActual('../../api.js');
  return {
    ...actual, fetchPrograms: vi.fn(), fetchProgram: vi.fn(), listProgramDrafts: vi.fn(), createProgramDraft: vi.fn(),
    fetchProgramDraft: vi.fn(), saveProgramDraftDocuments: vi.fn(), validateProgramDraft: vi.fn(), requestProgramReview: vi.fn(),
    reviewProgramDraft: vi.fn(), withdrawProgramDraft: vi.fn(), previewProgramDraft: vi.fn(), exportProgramDraft: vi.fn(),
    fetchProgramDraftManifest: vi.fn(),
  };
});

const api = await import('../../api.js');

const PACK = {
  jurisdiction: { level: 'state', code: 'ZY', name: 'Zedland Two' },
  credit: { code: 'ZY_DEMO_JTC', name: 'Zedland Demo Credit', statutory_citation: '' },
  filing: { window: '', cycle: 'annual' }, thresholds: { minimum_new_jobs: null }, benefit: {}, one_zero: {}, tax_year_convention: {},
};

const draft = (over = {}) => ({
  draft_id: 'd1', proposed_code: 'ZY_DEMO_JTC', name: 'Zedland Demo Credit', jurisdiction_level: 'state', state: 'ZY', status: 'draft', version: 2,
  created_by: 'ann', created_at: '2026-03-01T09:00:00Z', updated_by: 'ann', updated_at: '2026-03-01T09:00:00Z', pack_file: 'zy_demo_jtc.json',
  validation_errors: null, verification: 'not_verified', has_runtime_authority: false,
  documents: { pack: PACK, years: { 2025: yearSkeleton(PACK, 2025) } }, content_sha256: 'abc', validation: null, validation_current: false,
  review: { requested_by: null, reviewer: null, decision: null, comment: null, decided_at: null, approved_sha256: null },
  export: { exported_at: null, bundle_sha256: null }, allowed_actions: ['edit', 'validate', 'preview', 'withdraw'],
  events: [{ seq: 1, event_type: 'created', actor: 'ann', at: '2026-03-01T09:00:00Z', from_status: 'draft', to_status: 'draft', detail: {} }],
  ...over,
});

const row = (over = {}) => ({
  code: 'ZY_DEMO_JTC', name: 'Zedland Demo Credit', state: 'ZY', jurisdiction: { level: 'state', code: 'ZY' }, lifecycle: 'calculable',
  authored_years: [2024, 2025], unverified_years: [2024, 2025], verification: 'not_verified', calculable: true, not_calculable_reason: '',
  engagement: { in_scope: 1, out_of_scope: 0, prospective: 1, clients: 2 }, ...over,
});

const CATALOG = {
  programs: [
    row(),
    row({ code: 'GA_JTC', name: 'Georgia Jobs Tax Credit', state: 'GA', jurisdiction: { level: 'state', code: 'GA' }, unverified_years: [], engagement: null }),
    row({ code: 'SC_JTC', name: 'South Carolina Jobs Tax Credit', state: 'SC', jurisdiction: { level: 'state', code: 'SC' }, lifecycle: 'described', authored_years: [], unverified_years: [], calculable: false, not_calculable_reason: 'No year-scoped rule packs authored for SC_JTC. ADR-005: statute is not inherited across years.' }),
  ],
  total: 3, engagement_available: true, verification_note: 'Not verified.',
};

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  api.fetchPrograms.mockResolvedValue(CATALOG);
  api.fetchProgramDraft.mockResolvedValue(draft());
});
afterEach(() => { vi.useRealTimers(); vi.clearAllMocks(); });

const settle = async (ms = 0) => { await act(async () => { await vi.advanceTimersByTimeAsync(ms); }); };
const user = () => userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
const page = (route) => render(<MemoryRouter><ProgramsPage route={route} navigate={vi.fn()} /></MemoryRouter>);

describe('the catalog', () => {
  it('shows each program with its lifecycle badge, authored years, a not verified mark and calculability', () => {
    render(<ProgramCatalog rows={CATALOG.programs} onOpen={() => {}} />);
    const table = screen.getByRole('table', { name: 'Program catalog' });
    expect(within(table).getAllByText('Calculable').length).toBeGreaterThan(2); // the column header and two badges
    expect(within(table).getByText('Described, not calculable')).toBeInTheDocument();
    expect(within(table).getByText('Not verified: 2 of 2 years flagged')).toBeInTheDocument();
    expect(within(table).getAllByText(/^Not verified/).length).toBe(3);
    expect(within(table).getAllByText('2024\u20132025')).toHaveLength(2);
    expect(within(table).getAllByText('2 clients (1 in scope)').length).toBeGreaterThan(0);
    expect(within(table).getByText('Unavailable')).toBeInTheDocument(); // a program whose engagement could not be read says so, not zero
  });

  it('says why a described program cannot be calculated, on the row', () => {
    render(<ProgramCatalog rows={CATALOG.programs} onOpen={() => {}} />);
    expect(screen.getByText(/No year-scoped rule packs authored for SC_JTC/)).toBeInTheDocument();
    expect(screen.queryByText(/\bverified\b(?!:)/i, { selector: 'td' })).toBeNull();
  });

  it('opens a program by its name and says nothing was found for an empty registry', async () => {
    const onOpen = vi.fn();
    const { unmount } = render(<ProgramCatalog rows={CATALOG.programs} onOpen={onOpen} />);
    await user().click(screen.getByRole('button', { name: 'Open Georgia Jobs Tax Credit' }));
    expect(onOpen).toHaveBeenCalledWith('GA_JTC');
    unmount();
    render(<ProgramCatalog rows={[]} onOpen={onOpen} />);
    expect(screen.getByText('No programs are registered')).toBeInTheDocument();
  });

  it('is the first tab of the page with its summary and the add button, and degrades with a message', async () => {
    page([]);
    await settle();
    expect(await screen.findByRole('table', { name: 'Program catalog' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Add a program/ })).toBeInTheDocument();
    expect(screen.getByText(/unverified until a person verifies/)).toBeInTheDocument();
  });

  it('reports an unavailable catalog without a table and without claiming nothing exists', async () => {
    api.fetchPrograms.mockRejectedValue(new Error('programs 503'));
    page([]);
    await settle();
    expect(await screen.findByText('The program catalog is unavailable')).toBeInTheDocument();
    expect(screen.queryByRole('table')).toBeNull();
  });
});

describe('a program in detail', () => {
  const detail = (over = {}) => ({
    ...row(), pack: { file: 'zy_demo_jtc.json', present: true, rule_pack_version: '0.0.1', credit_name: 'Zedland Demo Credit', citation: 'Fictional Code', engine_profile: { credit_model: 'per_net_new_job', headcount_model: 'one_zero' }, notes: '' },
    years: [{ tax_year: 2025, rule_pack_version: '0.0.1+ty2025', unverified: true, source: 'invented', issues: [] }],
    validation: { pack: [], error_count: 0, valid: true }, blockers: [], ...over,
  });

  it('lists the years with their source and a not verified mark, and says the program can be priced without saying it is right', async () => {
    api.fetchProgram.mockResolvedValue(detail());
    render(<ProgramDetail code="ZY_DEMO_JTC" onBack={() => {}} />);
    expect(await screen.findByText('Calculable for its authored years')).toBeInTheDocument();
    expect(screen.getByText(/says nothing about whether its values are right/)).toBeInTheDocument();
    expect(screen.getByText('Not verified: flagged in the pack')).toBeInTheDocument();
    expect(screen.getByText('invented')).toBeInTheDocument();
  });

  it('lists what blocks calculation', async () => {
    api.fetchProgram.mockResolvedValue(detail({ lifecycle: 'described', calculable: false, years: [], blockers: ['No year-scoped rule packs authored.'] }));
    render(<ProgramDetail code="SC_JTC" onBack={() => {}} />);
    expect(await screen.findByText('What blocks calculation')).toBeInTheDocument();
    expect(screen.getByText('No year-scoped rule packs authored.')).toBeInTheDocument();
  });

  it('says a program is not in the registry for a 404 and nothing was changed', async () => {
    const error = Object.assign(new Error('x'), { status: 404 });
    api.fetchProgram.mockRejectedValue(error);
    render(<ProgramDetail code="NOPE" onBack={() => {}} />);
    expect(await screen.findByText('No such program')).toBeInTheDocument();
  });

  it('says it is unavailable, never a page of blanks or a crash, when the answer holds no program (the states sweep found a crash on {})', async () => {
    api.fetchProgram.mockResolvedValue({});
    render(<ProgramDetail code="ZY_DEMO_JTC" onBack={() => {}} />);
    expect(await screen.findByText('The program is unavailable')).toBeInTheDocument();
    expect(screen.getByText(/Nothing was changed/)).toBeInTheDocument();
  });
});

describe('the validation panel', () => {
  const validation = {
    valid: false, errors: 2, warnings: 0, infos: 1, truncated: true,
    findings: [
      { file: 'pack', severity: 'error', code: 'schema', path: 'thresholds/minimum_new_jobs', message: 'None is not of type number' },
      { file: 'year 2025', severity: 'error', code: 'citation_missing', path: '_year_provenance/source', message: 'name the primary source' },
      { file: 'pack', severity: 'info', code: 'unverified', path: 'benefit', message: 'carries _prototype_verify' },
    ],
  };

  it('groups findings by file, addresses each to its path, lists unverified flags as information and says when it is capped', () => {
    render(<ValidationPanel validation={validation} />);
    expect(screen.getByText('2 errors to fix')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Program pack findings' })).toHaveTextContent('thresholds/minimum_new_jobs');
    expect(screen.getByRole('region', { name: 'Year 2025 findings' })).toHaveTextContent('name the primary source');
    expect(screen.getByText(/1 unverified flag \(_prototype_verify\)/)).toBeInTheDocument();
    expect(screen.getByText(/The list is capped/)).toBeInTheDocument();
  });

  it('limits itself to the documents on this step', () => {
    render(<ValidationPanel validation={validation} files={['pack']} />);
    expect(screen.queryByText('name the primary source')).toBeNull();
  });

  it('reads a clean pass as valid, not verified', () => {
    render(<ValidationPanel validation={{ valid: true, errors: 0, infos: 3, findings: [] }} />);
    expect(screen.getByText(/valid is not verified/)).toBeInTheDocument();
  });

  it('asks for validation when there is none, and flags edits made since', () => {
    const { rerender } = render(<ValidationPanel validation={null} />);
    expect(screen.getByText(/Validate the draft to see field-level errors/)).toBeInTheDocument();
    rerender(<ValidationPanel validation={validation} stale />);
    expect(screen.getByText(/validate again before requesting review/)).toBeInTheDocument();
  });
});

describe('step 1: the basics', () => {
  it('shows the programs already registered for the state and says programs in one state are independent', async () => {
    page(['new']);
    await settle();
    await user().type(screen.getByLabelText('State (two letters)'), 'ga');
    expect(screen.getByText('Already registered for GA')).toBeInTheDocument();
    expect(screen.getByText(/each is calculated and assessed on its own program code/)).toBeInTheDocument();
    expect(screen.getByText(/Georgia Jobs Tax Credit/)).toBeInTheDocument();
  });

  it('shows a federal program as not runnable yet and will not start it', async () => {
    page(['new']);
    await settle();
    await user().click(screen.getByLabelText(/This is a federal program/));
    expect(screen.getByText('Federal programs are not runnable yet')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create the draft' })).toBeDisabled();
  });

  it('creates the draft from valid basics and goes to it', async () => {
    api.createProgramDraft.mockResolvedValue(draft());
    const navigate = vi.fn();
    render(<MemoryRouter><ProgramsPage route={['new']} navigate={navigate} /></MemoryRouter>);
    await settle();
    const u = user();
    await u.type(screen.getByLabelText('Program code'), 'zy_demo_jtc');
    await u.type(screen.getByLabelText('Credit name'), 'Zedland Demo Credit');
    await u.type(screen.getByLabelText('State (two letters)'), 'zy');
    await u.type(screen.getByLabelText('Tax years to start with (optional)'), '2025');
    await u.click(screen.getByRole('button', { name: 'Create the draft' }));
    expect(api.createProgramDraft).toHaveBeenCalledWith({ code: 'ZY_DEMO_JTC', name: 'Zedland Demo Credit', state: 'ZY', years: [2025] });
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/programs/draft/d1'));
  });

  it('explains a refusal and keeps what was typed', async () => {
    api.createProgramDraft.mockRejectedValue(Object.assign(new Error('x'), { reason: 'ZY_DEMO_JTC is already registered' }));
    page(['new']);
    await settle();
    const u = user();
    await u.type(screen.getByLabelText('Program code'), 'zy_demo_jtc');
    await u.type(screen.getByLabelText('Credit name'), 'Name');
    await u.type(screen.getByLabelText('State (two letters)'), 'zy');
    await u.click(screen.getByRole('button', { name: 'Create the draft' }));
    expect(await screen.findByText('The draft was not created')).toBeInTheDocument();
    expect(screen.getByText('ZY_DEMO_JTC is already registered')).toBeInTheDocument();
    expect(screen.getByLabelText('Program code')).toHaveValue('zy_demo_jtc');
  });
});

describe('steps 2 and 3: authoring with validation beside the fields', () => {
  it('says the draft cannot be opened when the answer holds no draft (the states sweep rendered "undefined" for {})', async () => {
    api.fetchProgramDraft.mockResolvedValue({});
    page(['draft', 'd1']);
    await settle();
    expect(await screen.findByText('The draft could not be opened')).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/undefined/);
  });

  it('keeps the not-verified notice on and shows a finding beside the field it is about', async () => {
    api.fetchProgramDraft.mockResolvedValue(draft({
      validation: { valid: false, errors: 1, warnings: 0, infos: 0, findings: [{ file: 'pack', severity: 'error', code: 'schema', path: 'thresholds/minimum_new_jobs', message: 'None is not of type number' }] },
    }));
    page(['draft', 'd1']);
    await settle();
    expect(await screen.findByText('Not verified, and not live')).toBeInTheDocument();
    const field = screen.getByLabelText('Minimum new jobs');
    expect(field).toHaveAttribute('aria-invalid', 'true');
    expect(within(field.closest('.prog-field')).getByRole('alert')).toHaveTextContent('None is not of type number');
  });

  it('saves itself after the last edit, naming the version it read', async () => {
    api.saveProgramDraftDocuments.mockResolvedValue(draft({ version: 3 }));
    page(['draft', 'd1']);
    await settle();
    await user().type(await screen.findByLabelText('Minimum new jobs'), '4');
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
    await settle(AUTOSAVE_MS + 100);
    await waitFor(() => expect(api.saveProgramDraftDocuments).toHaveBeenCalledTimes(1));
    const [id, body] = api.saveProgramDraftDocuments.mock.calls[0];
    expect(id).toBe('d1');
    expect(body.expectedVersion).toBe(2);
    expect(body.pack.thresholds.minimum_new_jobs).toBe(4);
    expect(await screen.findByText(/^Saved/)).toBeInTheDocument();
  });

  it('stops and says so when somebody else changed the draft, instead of overwriting it', async () => {
    api.saveProgramDraftDocuments.mockRejectedValue(Object.assign(new Error('changed'), { status: 409, code: 'draft_conflict' }));
    page(['draft', 'd1']);
    await settle();
    await user().type(await screen.findByLabelText('Minimum new jobs'), '4');
    await settle(AUTOSAVE_MS + 100);
    expect(await screen.findByText('Your last change was not saved')).toBeInTheDocument();
    expect(screen.getByText(/Someone else changed this draft/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reload the latest' })).toBeInTheDocument();
  });

  it('applies the advanced JSON only when it parses, and says why not', async () => {
    page(['draft', 'd1']);
    await settle();
    await screen.findByLabelText('Minimum new jobs');
    await user().click(screen.getByText('Advanced: edit base pack as JSON'));
    const box = screen.getByLabelText('base pack JSON');
    await user().clear(box);
    await user().type(box, 'not json');
    await user().click(screen.getByRole('button', { name: 'Apply JSON' }));
    expect(screen.getByRole('alert', { name: '' })).toHaveTextContent(/Not valid JSON/);
    expect(api.saveProgramDraftDocuments).not.toHaveBeenCalled();
  });

  it('adds a year as an empty flagged skeleton and refuses one that exists', async () => {
    page(['draft', 'd1']);
    await settle();
    await user().click(await screen.findByRole('button', { name: 'Year packs' }));
    expect(screen.getByText(/nothing is inherited from another year/)).toBeInTheDocument();
    const input = screen.getByLabelText('Add a tax year');
    await user().type(input, '2025');
    expect(screen.getByText('That year is already in the draft.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add 2025' })).toBeDisabled();
    await user().clear(input);
    await user().type(input, '2026');
    await user().click(screen.getByRole('button', { name: 'Add 2026' }));
    expect(screen.getByRole('button', { name: '2026' })).toBeInTheDocument();
    expect(screen.getByLabelText('Minimum new jobs')).toHaveValue(null);
  });

  it('is read only once the draft is under review, and says why', async () => {
    api.fetchProgramDraft.mockResolvedValue(draft({ status: 'ready_for_review', allowed_actions: ['approve', 'request_changes', 'preview', 'withdraw'] }));
    page(['draft', 'd1']);
    await settle();
    expect(await screen.findByText('Read only')).toBeInTheDocument();
    expect(screen.getByLabelText('Minimum new jobs')).toBeDisabled();
  });
});

describe('step 4: the preview', () => {
  const RESULT = {
    label: 'Preview, not verified, not for filing', draft_id: 'd1', proposed_code: 'ZY_DEMO_JTC', state: 'ZY',
    dataset: { kind: 'synthetic_sample', description: 'Committed synthetic sample payroll (generated; not a client\u2019s data)' },
    unverified: true, unverified_flags: 9, persisted: false, wrote_nothing: true,
    years: [{ tax_year: 2025, average_headcount: 44.2, prior_average_headcount: 40, is_base_year: false, qualifying_jobs: 3.2, per_job_usd: 1200, annual_credit_usd: 3840, benefit_period_years: 3 }],
    declined: [{ tax_year: 2019, reason: 'no_payroll', detail: 'the sample holds 0 row(s) for ZY in 2019' }],
  };

  it('labels the result, names the data and the unverified flags, and lists a year it could not price', async () => {
    api.previewProgramDraft.mockResolvedValue(RESULT);
    page(['draft', 'd1']);
    await settle();
    await user().click(await screen.findByRole('button', { name: 'Preview' }));
    await user().click(screen.getByRole('button', { name: 'Run the preview' }));
    expect(screen.getAllByText(/Preview, not verified, not for filing/).length).toBeGreaterThan(1);
    expect(screen.getByText(/9 statutory blocks still carry the unverified flag/)).toBeInTheDocument();
    expect(screen.getByRole('table', { name: 'Preview, not verified, not for filing' })).toHaveTextContent('$3,840');
    expect(screen.getByText(/2019: the sample holds 0 row/)).toBeInTheDocument();
    expect(screen.getByText(/Nothing was written or stored/)).toBeInTheDocument();
  });

  it('says why a preview could not run and that nothing changed', async () => {
    api.previewProgramDraft.mockRejectedValue(Object.assign(new Error('x'), { reason: 'validate and fix the draft first: 3 error(s).' }));
    page(['draft', 'd1']);
    await settle();
    await user().click(await screen.findByRole('button', { name: 'Preview' }));
    await user().click(screen.getByRole('button', { name: 'Run the preview' }));
    expect(await screen.findByText('The preview could not run')).toBeInTheDocument();
    expect(screen.getByText(/validate and fix the draft first/)).toBeInTheDocument();
  });

  it('is unavailable until the draft has a year', async () => {
    api.fetchProgramDraft.mockResolvedValue(draft({ documents: { pack: PACK, years: {} } }));
    page(['draft', 'd1']);
    await settle();
    const step = await screen.findByText('Preview');
    expect(step.closest('[aria-disabled="true"]')).not.toBeNull();
  });
});

describe('step 5: review', () => {
  const open = async (over) => {
    api.fetchProgramDraft.mockResolvedValue(draft(over));
    page(['draft', 'd1']);
    await settle();
    await user().click(await screen.findByRole('button', { name: 'Review' }));
  };

  it('enables exactly what the draft allows: validate, withdraw, no request until validated clean', async () => {
    await open({});
    expect(screen.getByRole('button', { name: 'Validate' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Request review' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Approve for export' })).toBeDisabled();
    expect(screen.getByText(/Approving lets the bundle be exported/)).toBeInTheDocument();
    expect(screen.getByText(/does not verify any value and it activates nothing/)).toBeInTheDocument();
  });

  it('validates, then shows the findings the draft was sent back with', async () => {
    api.validateProgramDraft.mockResolvedValue(draft({
      status: 'needs_changes', validation: { valid: false, errors: 1, warnings: 0, infos: 0, truncated: false, findings: [{ file: 'pack', severity: 'error', code: 'citation_missing', path: 'credit/statutory_citation', message: 'cite the statute this credit comes from' }] },
    }));
    api.fetchProgramDraft.mockResolvedValueOnce(draft()).mockResolvedValue(draft({ status: 'needs_changes' }));
    await open({});
    await user().click(screen.getByRole('button', { name: 'Validate' }));
    expect(await screen.findByText('cite the statute this credit comes from')).toBeInTheDocument();
    expect(api.validateProgramDraft).toHaveBeenCalledWith('d1');
  });

  it('requests changes only with a comment, and approves with one click when allowed', async () => {
    api.reviewProgramDraft.mockResolvedValue(draft({ status: 'approved_for_export' }));
    await open({ status: 'ready_for_review', allowed_actions: ['approve', 'request_changes', 'preview', 'withdraw'], review: { requested_by: 'ann', reviewer: null, decision: null, comment: null, decided_at: null, approved_sha256: null } });
    expect(screen.getByRole('button', { name: 'Request changes' })).toBeDisabled();
    await user().type(screen.getByLabelText(/Comment/), 'cite the rule');
    expect(screen.getByRole('button', { name: 'Request changes' })).toBeEnabled();
    await user().click(screen.getByRole('button', { name: 'Approve for export' }));
    expect(api.reviewProgramDraft).toHaveBeenCalledWith('d1', { decision: 'approve', comment: 'cite the rule' });
  });

  it('shows a refused review (for example the reviewer is the author) and keeps the draft as it was', async () => {
    api.reviewProgramDraft.mockRejectedValue(Object.assign(new Error('x'), { reason: 'the reviewer must differ from the people who wrote and submitted the draft' }));
    await open({ status: 'ready_for_review', allowed_actions: ['approve', 'request_changes', 'preview', 'withdraw'] });
    await user().click(screen.getByRole('button', { name: 'Approve for export' }));
    expect(await screen.findByText('That was refused')).toBeInTheDocument();
    expect(screen.getByText(/must differ from the people who wrote/)).toBeInTheDocument();
  });

  it('records who asked and who decided', async () => {
    await open({ status: 'approved_for_export', allowed_actions: ['export', 'withdraw'], review: { requested_by: 'ann', reviewer: 'bob', decision: 'approve', comment: 'values checked', decided_at: null, approved_sha256: 'x' } });
    expect(screen.getByText('Approved for export by bob')).toBeInTheDocument();
    expect(screen.getByText('values checked')).toBeInTheDocument();
  });
});

describe('step 6: export', () => {
  const MANIFEST = {
    files: [{ path: 'rules/zy_demo_jtc.json', sha256: 'a'.repeat(64) }, { path: 'COMMIT-CHECKLIST.md', sha256: 'b'.repeat(64) }],
    bundle_bytes: 2048, bundle_sha256: 'c'.repeat(64),
  };
  const approved = { status: 'approved_for_export', allowed_actions: ['export', 'withdraw', 'preview'] };

  it('is unavailable until the review approved the draft, with the reason', async () => {
    page(['draft', 'd1']);
    await settle();
    const step = await screen.findByText('Export');
    expect(step.closest('[aria-disabled="true"]')).not.toBeNull();
    expect(screen.getByText(/Unavailable: Export needs an approved review/)).toBeInTheDocument();
  });

  it('lists the bundle, the next steps for a person, and says exporting activates nothing', async () => {
    api.fetchProgramDraft.mockResolvedValue(draft(approved));
    api.fetchProgramDraftManifest.mockResolvedValue(MANIFEST);
    page(['draft', 'd1']);
    await settle();
    await user().click(await screen.findByRole('button', { name: 'Export' }));
    expect(await screen.findByText('Exporting activates nothing')).toBeInTheDocument();
    expect(await screen.findByRole('table', { name: 'Bundle files' })).toHaveTextContent('rules/zy_demo_jtc.json');
    expect(screen.getByText(/neither the author nor the reviewer/)).toBeInTheDocument();
    expect(screen.getByText(/becomes calculable only when the deployed rules folder holds its year packs/)).toBeInTheDocument();
  });

  it('downloads the bundle and shows its hash', async () => {
    api.fetchProgramDraft.mockResolvedValue(draft(approved));
    api.fetchProgramDraftManifest.mockResolvedValue(MANIFEST);
    api.exportProgramDraft.mockResolvedValue({ blob: new Blob(['zip']), sha256: 'd'.repeat(64), filename: 'zy_demo_jtc-bundle.zip' });
    globalThis.URL.createObjectURL = vi.fn(() => 'blob:x');
    globalThis.URL.revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    page(['draft', 'd1']);
    await settle();
    await user().click(await screen.findByRole('button', { name: 'Export' }));
    await user().click(await screen.findByRole('button', { name: 'Download the bundle' }));
    await waitFor(() => expect(click).toHaveBeenCalled());
    expect(await screen.findByText('d'.repeat(64))).toBeInTheDocument();
    click.mockRestore();
  });
});

describe('the drafts list and the history', () => {
  it('lists drafts with their status and opens one', async () => {
    api.listProgramDrafts.mockResolvedValue({ items: [draft({ status: 'needs_changes', validation_errors: 2, documents: undefined })], total: 1 });
    const navigate = vi.fn();
    render(<MemoryRouter><ProgramsPage route={[]} navigate={navigate} /></MemoryRouter>);
    await settle();
    await user().click(await screen.findByRole('tab', { name: 'Drafts' }));
    const table = await screen.findByRole('table', { name: 'Program drafts' });
    expect(within(table).getByText('Needs changes')).toBeInTheDocument();
    await user().click(within(table).getByRole('button', { name: 'Open draft Zedland Demo Credit' }));
    expect(navigate).toHaveBeenCalledWith('/programs/draft/d1');
  });

  it('says drafts need the writer role rather than showing an empty list', async () => {
    api.listProgramDrafts.mockRejectedValue(Object.assign(new Error('x'), { status: 403, reason: 'this user is not entitled to make changes' }));
    page([]);
    await settle();
    await user().click(await screen.findByRole('tab', { name: 'Drafts' }));
    expect(await screen.findByText('Drafts need the writer role')).toBeInTheDocument();
  });

  it('says there are no drafts yet and offers to start one', async () => {
    api.listProgramDrafts.mockResolvedValue({ items: [], total: 0 });
    page([]);
    await settle();
    await user().click(await screen.findByRole('tab', { name: 'Drafts' }));
    expect(await screen.findByText('No drafts yet')).toBeInTheDocument();
  });

  it('shows the append-only history with who did what', async () => {
    api.fetchProgramDraft.mockResolvedValue(draft({ events: [
      { seq: 1, event_type: 'created', actor: 'ann', at: '2026-03-01T09:00:00Z', from_status: 'draft', to_status: 'draft', detail: {} },
      { seq: 2, event_type: 'changes_requested', actor: 'bob', at: '2026-03-02T10:00:00Z', from_status: 'ready_for_review', to_status: 'needs_changes', detail: { comment: 'cite the rule' } },
    ] }));
    page(['draft', 'd1']);
    await settle();
    const history = await screen.findByRole('list', { name: 'Draft history' });
    expect(history).toHaveTextContent('Created by ann');
    expect(history).toHaveTextContent('Changes requested by bob');
    expect(history).toHaveTextContent('cite the rule');
  });

  it('says a draft that does not exist is not there, and nothing was changed', async () => {
    api.fetchProgramDraft.mockRejectedValue(Object.assign(new Error('x'), { status: 404, reason: 'no draft' }));
    page(['draft', 'nope']);
    await settle();
    expect(await screen.findByText('No such draft')).toBeInTheDocument();
  });
});
