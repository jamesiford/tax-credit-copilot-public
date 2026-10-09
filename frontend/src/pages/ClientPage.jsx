import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import TrendGridView from '../components/TrendGridView.jsx';
import Breadcrumb from '../components/Breadcrumb.jsx';
import ClaimPackageButton from '../components/ClaimPackageButton.jsx';
import ProgressView from '../components/ProgressView.jsx';
import PositionView from '../components/PositionView.jsx';
import PanelBoundary from '../components/PanelBoundary.jsx';
import SectionTabs, { SectionTabPanel } from '../components/SectionTabs.jsx';
import { PlanLevers, planJurisdiction } from '../components/PlanView.jsx';
import {
  addToStack, clientTab, DEFAULT_CLIENT_TAB, parseWhatIf, removeFromStack, stackEntry, stackPatch,
} from '../lib/whatIf.js';
import { placeholderYears } from '../lib/scopeDimension.js';
import {
  knownPeople, readSavedStack, rememberPerson, writeStack,
} from '../lib/whatIfStack.js';

/**
 * One client, whole: where the credit is earned, how much was claimed, how it
 * is tracking, and what would change it.
 *
 * Four sections, one visible at a time. They used to stack, which put What-if
 * four and a half screens below the grid it answers questions about — at 1024
 * x 768 nobody scrolls that far mid-demo. Tabs make each a click away, and a
 * Reading pill on the grid opens What-if already scoped to its location-year.
 *
 * The section is in the URL (`ctab`), with What-if's own scope (`wunit`,
 * `wyear`, `wmethod`, `wlever`, `wmag`, `wrun`), so a pasted link renders the
 * same section and the same projection cold. The location grid opens first
 * because it is the page's answer; the others are questions about it.
 *
 * A visited section stays mounted while hidden. Coming back to the grid must
 * not cost a warehouse read or lose which blocks were expanded.
 *
 * The employee-hours proximity cohort stays inside ProgressView, where the
 * backend already guarantees the two cannot disagree: `get_in_year_progress`
 * calls `handle_get_proximity` outright. The CLIENT-grain jobs list is a
 * different question and lives on the portfolio page.
 */
const TABS = [
  { id: 'location', label: 'Position by location', hint: 'Where credit is earned, location by location and year by year' },
  { id: 'claimed', label: 'What was claimed', hint: 'What was claimed against what they were entitled to' },
  { id: 'progress', label: 'How am I doing', hint: 'The year so far against the statutory finish line' },
  { id: 'whatif', label: 'What-if', hint: 'What would change the answer — for the client, or one location' },
];

const WHAT_IF_KEYS = ['wunit', 'wstack', 'wemp', 'wyear', 'wmethod', 'wlever', 'wmag', 'wrun'];

export default function ClientPage({
  clientName, onOpenPortfolio, scope, scopeOptions, scopeWindow, clientScope, ...rest
}) {
  const [search, setSearch] = useSearchParams();
  const active = clientTab(search);
  const whatIf = useMemo(() => parseWhatIf(search), [search]);

  const [visited, setVisited] = useState(() => new Set([active]));
  useEffect(() => {
    setVisited((prev) => (prev.has(active) ? prev : new Set([...prev, active])));
  }, [active]);

  const patchSearch = useCallback((patch) => {
    const next = new URLSearchParams(search);
    for (const [key, value] of Object.entries(patch)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    setSearch(next, { replace: false });
  }, [search, setSearch]);

  const onTab = useCallback((id) => {
    patchSearch({ ctab: id === DEFAULT_CLIENT_TAB ? '' : id });
  }, [patchSearch]);

  // A Reading pill replaces What-if's whole scope, not part of it — a lever
  // left over from the last location would be applied to this one.
  const onWhatIf = useCallback((link) => {
    if (!link) return;
    patchSearch({ ...Object.fromEntries(WHAT_IF_KEYS.map((k) => [k, ''])), ...link });
  }, [patchSearch]);

  // The employee STACK (28 Sep). Near the line adds to it one row at a time or
  // several at once; What-if projects it. Membership and starting figures are
  // in the URL while this page is open, and in the shared stack store
  // (`lib/whatIfStack.js`, 29 Sep) so a location's near-the-floor list and an
  // employee's walk can add to the same stack. Who each person is lives in
  // that store's memory, because a record token cannot be turned back into it.
  const stackScope = useMemo(
    () => ({ clientId: scope?.clientId, taxYear: whatIf.year, method: whatIf.method }),
    [scope?.clientId, whatIf.year, whatIf.method],
  );

  // Opened without a stack in the URL: take the saved one for this client, so
  // people added on another page are here. Replace, not push — this is the
  // same visit, not a new one.
  useEffect(() => {
    if (search.get('wstack')) return;
    const saved = readSavedStack();
    if (!saved?.entries?.length || String(saved.clientId) !== String(scope?.clientId)) return;
    const next = new URLSearchParams(search);
    for (const [key, value] of Object.entries(stackPatch(saved.entries, { taxYear: saved.taxYear, method: saved.method }))) {
      if (value) next.set(key, value); else next.delete(key);
    }
    setSearch(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope?.clientId]);

  // The URL is the source of truth while this page is open; the store follows.
  const wireStack = search.get('wstack') || '';
  useEffect(() => {
    if (wireStack && stackScope.taxYear != null) writeStack(stackScope, whatIf.stack);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wireStack, stackScope]);

  const stackContext = knownPeople();

  const onAddToStack = useCallback((rows, { taxYear, method }) => {
    const sameScope = whatIf.year === taxYear && whatIf.method === method;
    const next = addToStack(sameScope ? whatIf.stack : [], rows.map(stackEntry));
    rows.forEach(rememberPerson);
    patchSearch(stackPatch(next, { taxYear, method }));
  }, [whatIf.year, whatIf.method, whatIf.stack, patchSearch]);

  const onRemoveFromStack = useCallback((token) => {
    const next = removeFromStack(whatIf.stack, token);
    if (!next.length) writeStack(stackScope, []);
    patchSearch(stackPatch(next, { taxYear: whatIf.year, method: whatIf.method }));
  }, [whatIf.stack, whatIf.year, whatIf.method, patchSearch, stackScope]);

  const onOpenStack = useCallback(() => {
    patchSearch(stackPatch(whatIf.stack, { taxYear: whatIf.year, method: whatIf.method, open: true }));
  }, [whatIf.stack, whatIf.year, whatIf.method, patchSearch]);

  // From the What-if tab: a row removed (with the others' edits kept), or the
  // whole stack cleared, which goes back to the client-wide levers.
  const onChangeStack = useCallback((next) => {
    if (!next.length) writeStack(stackScope, []);
    patchSearch(stackPatch(next, { taxYear: whatIf.year, method: whatIf.method }));
  }, [whatIf.year, whatIf.method, patchSearch, stackScope]);

  const stack = useMemo(() => ({
    tokens: new Set(whatIf.stack.map((e) => e.token)),
    year: whatIf.year,
    method: whatIf.method,
    onAdd: onAddToStack,
    onRemove: onRemoveFromStack,
    onOpen: onOpenStack,
  }), [whatIf.stack, whatIf.year, whatIf.method, onAddToStack, onRemoveFromStack, onOpenStack]);

  const onChangeUnit = useCallback((unitId) => {
    patchSearch({ wunit: unitId || '', wstack: '', wemp: '', wlever: '', wmag: '', wrun: '' });
  }, [patchSearch]);

  // WI-20. "You need to know the industry and the tier" — the tier is on every
  // location-year; the industry is the client's, so it sits beside the name.
  const industry = (scopeOptions?.clients || [])
    .find((c) => String(c.account_id) === String(scope?.clientId))?.industry || null;

  // How am I doing and What-if are questions about the year still RUNNING, so
  // they open on the client's open year when it holds one (TY2026). The grid
  // keeps every year; the shell's year stays the latest complete one.
  const openYears = clientScope?.open_years || [];
  const currentYear = openYears.length ? openYears[openYears.length - 1] : scope?.year;

  const trail = [
    { key: 'p', label: 'Portfolio', onClick: onOpenPortfolio },
    {
      key: 'c',
      label: clientName || 'This client',
      badge: industry
        ? <span className="pill pill-neutral" title="Industry — shown, not applied by the engine">{industry}</span>
        : null,
    },
  ];

  const leverScope = useMemo(
    () => ({ ...scope, year: currentYear, jurisdiction: planJurisdiction(scope, scopeOptions) }),
    [scope, scopeOptions, currentYear],
  );
  const progressScope = useMemo(() => ({ ...scope, year: currentYear }), [scope, currentYear]);
  const placeholderFloor = placeholderYears(scopeOptions, scope?.programCode).includes(currentYear);
  const floorNote = placeholderFloor ? (
    <p className="callout warn" role="note">
      <b>TY{currentYear}&apos;s wage floor is a placeholder.</b> Georgia has not published it
      yet, so the TY{currentYear - 1} floor is carried forward until it is. Every
      TY{currentYear} figure on this tab rests on it.
    </p>
  ) : null;

  const panel = (id) => ({
    id, active, idPrefix: 'client', keepMounted: true, visited: visited.has(id),
  });

  return (
    <div>
      <Breadcrumb trail={trail} />
      <ClaimPackageButton clientId={scope?.clientId} taxYear={scope?.year} />
      <div className="tcc-client-tabs">
        <SectionTabs tabs={TABS} active={active} onChange={onTab} label="Client sections" idPrefix="client" />
      </div>

      {/* Each panel is boundaried so one failing costs a panel, not the page —
          this page rendered completely blank when ProximityView threw inside
          ProgressView. */}
      <SectionTabPanel {...panel('location')}>
        <PanelBoundary name="Position by location">
          <TrendGridView
            scope={scope}
            scopeOptions={scopeOptions}
            clientScope={clientScope}
            onWhatIf={onWhatIf}
            {...rest}
          />
        </PanelBoundary>
      </SectionTabPanel>

      <SectionTabPanel {...panel('claimed')}>
        <PanelBoundary name="What was claimed">
          <PositionView
            embedded
            scope={scope}
            scopeWindow={scopeWindow}
            scopeOptions={scopeOptions}
            clientScope={clientScope}
          />
        </PanelBoundary>
      </SectionTabPanel>

      <SectionTabPanel {...panel('progress')}>
        <PanelBoundary name="How am I doing">
          {floorNote}
          <ProgressView scope={progressScope} scopeOptions={scopeOptions} stack={stack} yearOpen={openYears.includes(currentYear)} />
        </PanelBoundary>
      </SectionTabPanel>

      <SectionTabPanel {...panel('whatif')}>
        <PanelBoundary name="What-if">
          {(whatIf?.year ?? currentYear) === currentYear ? floorNote : null}
          <PlanLevers
            scope={leverScope}
            clientName={clientName || `Account ${scope?.clientId}`}
            whatIf={whatIf}
            onChangeUnit={onChangeUnit}
            stackContext={stackContext}
            onChangeStack={onChangeStack}
          />
        </PanelBoundary>
      </SectionTabPanel>
    </div>
  );
}
