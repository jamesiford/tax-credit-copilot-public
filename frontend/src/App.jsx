import { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Binary, BookOpenCheck, ChevronLeft, ClipboardList, Database, FileDiff,
  Menu, MessageSquare, Play, RefreshCw, ShieldCheck,
  ShieldQuestion, Users, X,
} from 'lucide-react';
import { fetchClientScope, fetchScope, fetchWorkspace, hasYear, refreshWorkspace } from './api.js';
import AgentActivityView from './components/AgentActivityView.jsx';
import ChatPanel from './components/ChatPanel.jsx';
import DataIngestionView from './components/DataIngestionView.jsx';
import EvidenceView from './components/EvidenceView.jsx';
import RuleLibraryView from './components/RuleLibraryView.jsx';
import ScopeBar from './components/ScopeBar.jsx';
import TopScope from './components/TopScope.jsx';
import SideRail from './components/SideRail.jsx';
import ClientPage from './pages/ClientPage.jsx';
import EmployeePage from './pages/EmployeePage.jsx';
import PortfolioPage from './pages/PortfolioPage.jsx';
import UnitPage from './pages/UnitPage.jsx';
import {
  PORTFOLIO, loadStoredScope, reconcileScope, scopeLabel, storeScope,
} from './lib/scopeDimension.js';
import { TOUR_DEFAULT_DWELL_MS, TOUR_STEPS } from './lib/tour.js';
import { brand } from './brand.config.js';
import {
  AssumptionsView, CompareView, EligibilityView, OneZeroView,
} from './components/ReferenceViews.jsx';

/**
 * The navigation IS the story.
 *
 * Five sections that read as a sentence rather than as a menu: what is this
 * worth, is it on track, what needs a decision, what would change it, prove it.
 * Someone who has never seen the product should be able to read the sidebar top
 * to bottom and understand what the tool does.
 *
 * Order is narrative first, then frequency of need. Ingestion and findings sat
 * last under "How it runs" — a heading left over from when Agent activity listed
 * registered agents and their status. Both were rebuilt into decision queues:
 * ingestion carries accept/drop/flag on every QC exception, findings carry
 * resolve/reopen, and the code counts `requires_decision`. They are what an
 * analyst opens most often, so they are no longer filed under plumbing.
 *
 * **An entry earns its place by answering a question no other entry answers.**
 * Three did not, and were folded into the page that already summarised them:
 *
 *   - `proximity` into `progress`. Never two cohorts — `get_in_year_progress`
 *     calls `handle_get_proximity` outright so the two could not disagree, and
 *     Progress rendered eight rows of the same list with the method locked to
 *     Min-Max. The full cohort is embedded there now, controls intact.
 *   - `provenance` and `walk` into `evidence`. All three read the same two
 *     singleton endpoints, and the pack already carried a hashes panel that
 *     repeated run identity value for value plus a table that repeated the
 *     walk. Full working sits behind a toggle so the printed pack stays short.
 *
 * `sealed` marks views backed by the CERTIFIED PARITY RUN rather than by the
 * client selector. Be honest about what that covers, because it is two things:
 *
 *   - `compare` genuinely has one subject. There is no Access output for any
 *     client but the reference one, so following the selector is meaningless.
 *   - `evidence` SHOULD exist per client-year and does not yet. It reads the
 *     singleton `/api/workspace/*`. That is a gap, not a principle, and
 *     `eligibility` and `onezero` are the proof: both now follow the selector
 *     via `/api/eligibility/{tax_year}` and `/api/onezero/matrix/{tax_year}`,
 *     which resolve statute, fiscal window and methodology as three separate
 *     lookups against the client's own records. Folding provenance and the walk
 *     into the pack means that conversion is now one view, not three.
 *
 * `clientAgnostic` marks a sealed view that is not client-scoped at all.
 * Methodology is the only one: BA-01..BA-12 are global and the statutory floors
 * are year-scoped, so telling a viewer it "describes Candle Bottle" was simply
 * wrong.
 */
export const NAV = [
  { section: 'What is it worth', items: [
    { id: 'eligibility', label: 'Eligibility', icon: Users, primary: true },
    { id: 'onezero', label: 'Monthly employment', icon: Binary },
  ] },
  { section: 'What needs a decision', items: [
    { id: 'ingestion', label: 'Payroll data', icon: Database },
    { id: 'agents', label: 'Agents', icon: ShieldQuestion },
  ] },
  { section: 'Prove it', items: [
    { id: 'evidence', label: 'Audit trail', icon: ClipboardList, primary: true, sealed: true },
    { id: 'compare', label: 'Back-test', icon: FileDiff, sealed: true },
    { id: 'rules', label: 'Programs', icon: BookOpenCheck },
    { id: 'assumptions', label: 'Calculations', icon: ShieldCheck, sealed: true, clientAgnostic: true },
  ] },
];

// `trend` is no longer a nav entry but remains the default route view: it is
// what `/` and `/c/:id` resolve to, now rendered as PortfolioPage/ClientPage.
const ROUTE_ONLY_VIEWS = ['trend'];

const ALL_ITEMS = NAV.flatMap((group) => group.items);
const ALL_VIEW_IDS = new Set([...ALL_ITEMS.map((item) => item.id), ...ROUTE_ONLY_VIEWS]);

function normalizeClientId(value) {
  if (value == null || value === PORTFOLIO || value === 'portfolio') return PORTFOLIO;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : value;
}

function buildRouteUrl({ clientId = PORTFOLIO, view = 'trend', unitId = null, token = null, year = null, month = null, method = null, unit = null, sealed = false }) {
  const search = new URLSearchParams();
  if (year != null && Number.isFinite(Number(year))) search.set('year', String(Number(year)));
  if (month != null && month !== '') search.set('month', String(month));
  if (method) search.set('method', String(method));
  // Which unit the employee was opened from, so the breadcrumb can walk back.
  if (unit) search.set('unit', String(unit));
  // A token minted by the certified run resolves only there. Without this flag a
  // sealed drill opened under a client scope would be re-read as that client's.
  if (sealed) search.set('sealed', '1');

  const base = clientId === PORTFOLIO ? '/' : `/c/${encodeURIComponent(clientId)}`;
  let pathname = base;
  if (token) pathname = `${base}/e/${encodeURIComponent(token)}`;
  else if (unitId) pathname = `${base}/u/${encodeURIComponent(unitId)}`;
  else if (view && view !== 'trend') pathname = clientId === PORTFOLIO ? `/${view}` : `${base}/${view}`;

  const query = search.toString();
  return `${pathname}${query ? `?${query}` : ''}`;
}

function parseRouteState(pathname) {
  const clean = pathname.replace(/^\/+|\/+$/g, '');
  const segments = clean ? clean.split('/') : [];
  const clientIndex = segments[0] === 'c' ? 1 : null;
  const clientId = clientIndex != null && segments[clientIndex] ? normalizeClientId(segments[clientIndex]) : null;
  const token = clientId && segments[2] === 'e' ? decodeURIComponent(segments[3] || '') : null;
  const unitId = clientId && segments[2] === 'u' ? decodeURIComponent(segments[3] || '') : null;

  let view = 'trend';
  if (clientId != null) {
    if (segments[2] && segments[2] !== 'e' && segments[2] !== 'u') {
      view = ALL_VIEW_IDS.has(segments[2]) ? segments[2] : 'trend';
    }
  } else if (segments[0] && ALL_VIEW_IDS.has(segments[0])) {
    view = segments[0];
  }

  return { clientId, token, unitId, view, isRoot: segments.length === 0 };
}

function scrollToTop() {
  const scroll = window.scrollTo;
  if (typeof scroll !== 'function') return;
  if (String(scroll).includes('not implemented')) return;
  scroll.call(window, { top: 0, behavior: 'smooth' });
}

/** Page-scoped prompts. Kept here so a view does not have to know about chat. */
const ASK = {
  trend: 'Which of this client\u2019s locations dipped below the minimum-new-jobs threshold, and in which years?',
  position: 'Summarize what this client is entitled to against what they have claimed, and where the biggest recoverable gap is.',
  progress: 'Summarize how this client is tracking against the statutory threshold part-way through the year, and which employees are closest to qualifying.',
  plan: 'Summarize which lever moves this client\u2019s credit the most, and by how much.',
};

//: At portfolio scope there is no client, so every prompt above is the wrong
//: question — "which of THIS CLIENT's locations" asked while looking at the
//: whole book reads as a bug. The book has its own question, and it is the one
//: people actually open the drawer to ask.
const ASK_PORTFOLIO =
  'Who should we be targeting, and why? Rank them and say what I would open the call with.';

function askForPage(routeView, isPortfolio) {
  return isPortfolio ? ASK_PORTFOLIO : ASK[routeView];
}

function ShellLoading() {
  return <div className="tcc-shell-state"><div className="tcc-loader" /><h1>Opening the calculation workspace</h1><p>Reading payroll and rebuilding the sealed run.</p></div>;
}

export default function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const search = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const route = useMemo(() => parseRouteState(location.pathname), [location.pathname]);
  const routeClientId = route.clientId;
  const routeIsRoot = route.isRoot;
  const routeView = useMemo(() => {
    if (route.token) return 'trend';
    return route.view || 'trend';
  }, [route.token, route.view]);
  const routeYear = useMemo(() => {
    const value = Number(search.get('year'));
    return Number.isFinite(value) ? value : null;
  }, [search]);
  const routeEmployeeToken = route.token ?? null;
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [employeeToken, setEmployeeToken] = useState(() => routeEmployeeToken ?? null);
  // A token resolves only where the run that minted it is served. Sealed views
  // pass no context; per-client views pass the client-year they rendered.
  const [employeeContext, setEmployeeContext] = useState(null);
  const [navOpen, setNavOpen] = useState(false);

  const [chatOpen, setChatOpen] = useState(false);
  const [queuedPrompt, setQueuedPrompt] = useState(null);
  const [queuedScope, setQueuedScope] = useState(null);

  const [tourActive, setTourActive] = useState(false);
  const [tourStep, setTourStep] = useState(0);
  const [tourPaused, setTourPaused] = useState(false);

  // Scope lives in the shell, not in a view, because it survives navigation.
  // Moving between Eligibility and One/Zero must not reset which client you are
  // looking at — that is the whole point of scope being a dimension.
  const [scope, setScope] = useState(() => {
    const fallback = loadStoredScope();
    return {
      ...fallback,
      clientId: routeClientId ?? fallback.clientId,
      year: routeYear ?? fallback.year,
    };
  });
  const [scopeOptions, setScopeOptions] = useState(null);
  const [clientScope, setClientScope] = useState(null);
  const [clientError, setClientError] = useState(null);
  const [clientLoading, setClientLoading] = useState(false);
  const [scopeLoading, setScopeLoading] = useState(true);

  const load = async (force = false) => {
    setError(null);
    if (force) setRefreshing(true);
    try { setSummary(force ? await refreshWorkspace() : await fetchWorkspace()); }
    catch (reason) { setError(String(reason)); }
    finally { setRefreshing(false); }
  };

  useEffect(() => { load(); }, []);

  useEffect(() => {
    let cancelled = false;
    fetchScope()
      .then((options) => { if (!cancelled) setScopeOptions(options); })
      .catch((reason) => { if (!cancelled) setClientError(String(reason)); })
      .finally(() => { if (!cancelled) setScopeLoading(false); });
    return () => { cancelled = true; };
  }, []);

  // One client's own facts — states, row count, which years it holds payroll
  // for. Fetched on client change rather than up front: at portfolio scope
  // there is no single client to describe.
  //
  // The previous client's facts are cleared BEFORE the fetch, not after it
  // resolves. A cold Fabric read is ~55s (ten Delta opens), and leaving the old
  // numbers on screen under the new client's name for that long is the same
  // error the API refuses to make: one client's figures presented as another's.
  useEffect(() => {
    if (scope.clientId === PORTFOLIO) {
      setClientScope(null); setClientError(null); setClientLoading(false);
      return undefined;
    }
    let cancelled = false;
    setClientScope(null);
    setClientError(null);
    setClientLoading(true);
    fetchClientScope(scope.clientId)
      .then((detail) => { if (!cancelled) setClientScope(detail); })
      .catch((reason) => { if (!cancelled) { setClientScope(null); setClientError(String(reason)); } })
      .finally(() => { if (!cancelled) setClientLoading(false); });
    return () => { cancelled = true; };
  }, [scope.clientId]);

  useEffect(() => {
    const fallback = loadStoredScope();
    setScope((current) => {
      const next = {
        ...current,
        // `/` is not "the URL omits the client" — it POSITIVELY means the book.
        // Falling back to the stored client there rendered Cascade under the
        // portfolio's own URL, which is the one thing the routing rule forbids.
        // A view path with no client (`/position`) still restores.
        clientId: routeIsRoot
          ? PORTFOLIO
          : routeClientId ?? current.clientId ?? fallback.clientId,
        year: routeYear ?? current.year ?? fallback.year,
      };
      if (
        current.clientId === next.clientId
        && current.year === next.year
        && current.programCode === next.programCode
        && current.windowMode === next.windowMode
      ) return current;
      return next;
    });
  }, [routeClientId, routeIsRoot, routeYear]);

  useEffect(() => {
    setEmployeeToken(routeEmployeeToken ?? null);
  }, [routeEmployeeToken]);

  const resolved = useMemo(
    () => reconcileScope(scope, scopeOptions, clientScope),
    [scope, scopeOptions, clientScope],
  );

  // Persist the RESOLVED scope, not the requested one: reloading into a
  // selection the data cannot honour would reproduce the same notice forever.
  useEffect(() => { storeScope(resolved.scope); }, [resolved.scope]);

  const openEmployee = useCallback((token, context = null) => {
    const next = buildRouteUrl({
      clientId: scope.clientId,
      view: routeView,
      token,
      year: scope.year,
      month: search.get('month'),
      method: search.get('method'),
      sealed: !context,
    });
    setEmployeeContext(context);
    setEmployeeToken(token);
    navigate(next);
  }, [navigate, routeView, scope.clientId, scope.year, search]);

  const changeScope = useCallback((next) => {
    const target = typeof next === 'function' ? next(scope) : next;
    setScope(target);
    const url = buildRouteUrl({
      clientId: target.clientId,
      view: routeView,
      year: target.year,
      month: search.get('month'),
      method: search.get('method'),
    });
    navigate(url);
  }, [navigate, routeView, scope, search]);

  const navigateToView = useCallback((view) => {
    const url = buildRouteUrl({
      clientId: scope.clientId,
      view,
      year: scope.year,
      month: search.get('month'),
      method: search.get('method'),
    });
    navigate(url);
    setNavOpen(false);
    scrollToTop();
  }, [navigate, scope.clientId, scope.year, search]);

  const ask = useCallback((prompt, scopeOverride) => {
    setQueuedPrompt(prompt);
    // A row-level ask answers about THAT client without moving the user's
    // selection. Reusing the shell scope would answer about whoever happens to
    // be selected, under the heading of whoever they clicked.
    setQueuedScope(scopeOverride || null);
    setChatOpen(true);
  }, []);

  const exitTour = useCallback(() => {
    setTourActive(false);
    setTourPaused(false);
  }, []);

  const startTour = useCallback(() => {
    setTourStep(0);
    setTourPaused(false);
    setTourActive(true);
  }, []);

  useEffect(() => {
    if (!tourActive) return undefined;
    const step = TOUR_STEPS[tourStep];
    if (!step) { setTourActive(false); return undefined; }
    const nextScope = step.scope ? { ...scope, ...step.scope } : scope;
    setScope(nextScope);
    navigate(buildRouteUrl({
      clientId: nextScope.clientId,
      view: step.view,
      year: nextScope.year,
      month: search.get('month'),
      method: search.get('method'),
    }));
    if (tourPaused) return undefined;
    const id = setTimeout(
      () => {
        if (tourStep + 1 < TOUR_STEPS.length) setTourStep((s) => s + 1);
        else setTourActive(false);
      },
      step.dwell_ms || TOUR_DEFAULT_DWELL_MS,
    );
    return () => clearTimeout(id);
  }, [tourActive, tourStep, tourPaused, scope, navigate, search]);

  useEffect(() => {
    const handler = (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setQueuedPrompt(null);
        setChatOpen((v) => !v);
        return;
      }
      if (event.key !== 'Escape') return;
      if (tourActive) exitTour();
      // The drill is a route now, so Escape is a step back up it.
      else if (route.token || route.unitId) navigate(-1);
      else if (chatOpen) setChatOpen(false);
      else setNavOpen(false);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [route.token, route.unitId, navigate, chatOpen, tourActive, exitTour]);

  const activeItem = useMemo(() => ALL_ITEMS.find((i) => i.id === routeView), [routeView]);

  const clientDisplayName = useMemo(() => {
    if (resolved.scope.clientId === PORTFOLIO) return null;
    const match = (scopeOptions?.clients || [])
      .find((c) => String(c.account_id) === String(resolved.scope.clientId));
    return match?.name || `Account ${resolved.scope.clientId}`;
  }, [resolved.scope.clientId, scopeOptions]);

  if (!summary && !error) return <ShellLoading />;
  if (!summary && error) return <div className="tcc-shell-state error"><ShieldCheck size={38} /><h1>Workspace unavailable</h1><p>{error}</p><button className="btn btn-primary" onClick={() => load()}>Retry</button></div>;

  const common = {
    summary,
    navigate,
    openEmployee,    scope: resolved.scope,
    scopeWindow: resolved.window,
    scopeOptions,
    clientScope,
  };

  // A sealed view describes the certified run whatever the selector says. Both
  // dimensions have to be checked: a year mismatch used to pass silently, which
  // is worse than the client case because nothing on screen looks wrong.
  const sealedAccount = summary?.workspace?.account_id;
  const sealedYear = summary?.workspace?.tax_year;
  const clientDiffers = activeItem?.sealed
    && !activeItem?.clientAgnostic
    && sealedAccount != null
    && String(resolved.scope.clientId) !== String(sealedAccount);
  const yearDiffers = activeItem?.sealed
    && sealedYear != null
    && Number(resolved.scope.year) !== Number(sealedYear);
  const sealedMismatch = clientDiffers || yearDiffers;

  let view;
  // Which of the four drill pages is showing. The chrome uses it to decide
  // whether the year selector filters anything here.
  const page = route.token ? 'employee'
    : route.unitId ? 'unit'
      : route.clientId && route.clientId !== PORTFOLIO ? 'client'
        : 'portfolio';

  // The drill is four routes now, not a view with overlays on top. Token first:
  // an employee is reachable from a unit, a client, or the sealed run, and the
  // URL is what says which.
  //
  // The token was minted for the year in the URL, so that year is the
  // authority on the employee page. The resolved scope is `null` until the
  // client's payroll loads, which posted the drill with no year on every cold
  // open of a shared link.
  const employeeYear = hasYear(search.get('year')) ? Number(search.get('year')) : resolved.scope.year;
  if (route.token) {
    view = <EmployeePage
      clientId={search.get('sealed') === '1' ? null : route.clientId}
      token={route.token}
      year={employeeYear}
      method={search.get('method') || 'min_max'}
      clientName={clientDisplayName}
      unitId={search.get('unit')}
      onOpenPortfolio={() => navigate(buildRouteUrl({ clientId: PORTFOLIO }))}
      onOpenClient={() => navigate(buildRouteUrl({ clientId: route.clientId, year: resolved.scope.year }))}
      onOpenUnit={() => navigate(buildRouteUrl({
        clientId: route.clientId, unitId: search.get('unit'),
        year: resolved.scope.year, month: search.get('month'), method: search.get('method'),
      }))}
      onOpenWhatIf={(href) => navigate(href)}
      onBack={() => navigate(-1)}
    />;
  }
  else if (route.unitId) {
    view = <UnitPage
      clientId={route.clientId}
      unitId={route.unitId}
      year={resolved.scope.year}
      month={search.get('month') ? Number(search.get('month')) : null}
      method={search.get('method') || 'min_max'}
      clientName={clientDisplayName}
      onOpenPortfolio={() => navigate(buildRouteUrl({ clientId: PORTFOLIO }))}
      onOpenClient={() => navigate(buildRouteUrl({ clientId: route.clientId, year: resolved.scope.year }))}
      onChangeMonth={(month) => navigate(buildRouteUrl({
        clientId: route.clientId, unitId: route.unitId,
        year: resolved.scope.year, month, method: search.get('method'),
      }))}
      onChangeMethod={(method) => navigate(buildRouteUrl({
        clientId: route.clientId, unitId: route.unitId,
        year: resolved.scope.year, month: search.get('month'), method,
      }))}
      onOpenEmployee={(token) => navigate(buildRouteUrl({
        clientId: route.clientId, token, year: resolved.scope.year,
        month: search.get('month'), method: search.get('method'), unit: route.unitId,
      }))}
    />;
  }
  else if (routeView === 'trend' && resolved.scope.clientId === PORTFOLIO) {
    view = <PortfolioPage
      scope={resolved.scope}
      scopeWindow={resolved.window}
      scopeOptions={scopeOptions}
      clientScope={clientScope}
      onPickClient={(clientId) => changeScope({ ...resolved.scope, clientId })}
      onAskCopilot={ask}
    />;
  }
  else if (routeView === 'trend') {
    view = <ClientPage
      clientName={clientDisplayName}
      onOpenPortfolio={() => navigate(buildRouteUrl({ clientId: PORTFOLIO }))}
      scope={resolved.scope}
      scopeWindow={resolved.window}
      scopeOptions={scopeOptions}
      clientScope={clientScope}
      scopeError={clientError}
      onPickClient={(clientId) => changeScope({ ...resolved.scope, clientId })}
      onOpenUnit={(unitId, { year, month, method }) => navigate(buildRouteUrl({
        clientId: resolved.scope.clientId, unitId, year, month, method,
      }))}
    />;
  }
  else if (routeView === 'eligibility') view = <EligibilityView {...common} scope={resolved.scope} />;
  else if (routeView === 'onezero') view = <OneZeroView {...common} scope={resolved.scope} />;
  else if (routeView === 'compare') view = <CompareView {...common} />;
  else if (routeView === 'assumptions') view = <AssumptionsView {...common} />;
  else if (routeView === 'rules') view = <RuleLibraryView onAskCopilot={ask} programs={scopeOptions?.programs ?? null} />;
  else if (routeView === 'evidence') view = <EvidenceView summary={summary} onAskCopilot={ask} />;
  else if (routeView === 'ingestion') {
    view = <DataIngestionView
      taxYear={resolved.scope.year}
      accountId={resolved.scope.clientId === PORTFOLIO ? null : resolved.scope.clientId}
    />;
  }
  else if (routeView === 'agents') view = <AgentActivityView scope={resolved.scope} scopeOptions={scopeOptions} />;
  // Findings used to be the bare `else`, so a nav entry whose route was removed
  // rendered the findings queue under someone else's heading rather than
  // failing. Three entries were just merged away; the next removal should say so.
  else {
    view = (
      <div className="callout warn">
        <b>No view is wired to &ldquo;{routeView}&rdquo;.</b> The navigation
        offers it and the shell cannot render it, which means a nav entry
        outlived its route.
      </div>
    );
  }

  const label = scopeLabel(resolved.scope, scopeOptions, clientScope);
  const step = tourActive ? TOUR_STEPS[tourStep] : null;

  return <div className="tcc-app tcc-has-rail">
    <header className="tcc-topbar">
      <button
        className="tcc-mobile-menu"
        onClick={() => setNavOpen((v) => !v)}
        aria-label="Navigation"
      >
        <Menu size={20} />
      </button>
      <div className="tcc-brand"><img src={brand.logoSrc} alt={brand.name} /><span /><b>{brand.name}</b></div>
      <div className="tcc-top-context">
        {/* TY and method persist across a drill; the client comes from the URL. */}
        <TopScope
          page={page}
          options={scopeOptions}
          scope={resolved.scope}
          resolved={resolved}
          clientScope={clientScope}
          error={clientError}
          onChange={changeScope}
        />
        <button className="tcc-top-btn" onClick={() => { setQueuedPrompt(null); setChatOpen(true); }} title="Ask Copilot (Ctrl+K)">
          <MessageSquare size={15} /><span>Ask</span>
        </button>
      </div>
    </header>

    {navOpen && (
      <button
        className="tcc-nav-scrim"
        onClick={() => setNavOpen(false)}
        aria-label="Close navigation"
      />
    )}

    {/* The rail reads the ROUTE, not a second copy of it, so it cannot
        disagree with the page about where you are. */}
    <SideRail
      clientId={route.clientId}
      clientName={clientDisplayName}
      unitId={route.unitId}
      token={route.token}
      view={routeView}
      open={navOpen}
      onClose={() => setNavOpen(false)}
      onOpenPortfolio={() => { setNavOpen(false); navigate(buildRouteUrl({ clientId: PORTFOLIO })); }}
      onOpenClient={() => {
        setNavOpen(false);
        navigate(buildRouteUrl({ clientId: route.clientId, year: resolved.scope.year }));
      }}
      onOpenUnit={() => {
        setNavOpen(false);
        navigate(buildRouteUrl({
          clientId: route.clientId,
          unitId: route.unitId || search.get('unit'),
          year: resolved.scope.year,
          month: search.get('month'),
          method: search.get('method'),
        }));
      }}
      onSelectView={navigateToView}
    />

    <main className="tcc-main" aria-label={activeItem?.label || 'Position'}>
      {error && <div className="callout warn">Refresh failed; the last sealed run remains active. {error}</div>}
      {sealedMismatch && (
        <div className="callout info">
          <b>This is the certified parity run.</b> It describes{' '}
          {clientDiffers ? summary.workspace.client_name : 'this client'}
          {yearDiffers ? ` for tax year ${summary.workspace.tax_year}` : ''} and
          does not follow the selector — it is the artifact tied out against
          the partner's own calculation, so it stays fixed.{' '}
          {activeItem?.clientAgnostic
            ? 'Calculations are not client-specific; only the tax year differs.'
            : 'A per-client audit trail is the next step; today this view exists for the certified run only.'}
        </div>
      )}
      {view}
    </main>

    {step && (
      <div className="tour-bar">
        {/* Inline because the width is COMPUTED from tour position; a class
            cannot carry a per-render percentage. */}
        <div className="tour-progress" style={{ width: `${((tourStep + 1) / TOUR_STEPS.length) * 100}%` }} />
        <div className="tour-bar-row">
          <div className="tour-bar-meta">
            <div className="tour-step-num">Step {tourStep + 1} of {TOUR_STEPS.length}</div>
            <div className="tour-step-title">{step.title}</div>
            <div className="tour-step-summary">{step.summary}</div>
          </div>
          <div className="tour-bar-actions">
            <button className="btn btn-secondary" disabled={!tourStep} onClick={() => setTourStep((s) => Math.max(0, s - 1))}>Back</button>
            <button className="btn btn-secondary" onClick={() => setTourPaused((p) => !p)}>
              {tourPaused ? 'Resume' : 'Pause'}
            </button>
            <button className="btn btn-secondary" onClick={() => (tourStep + 1 < TOUR_STEPS.length ? setTourStep((s) => s + 1) : exitTour())}>Next</button>
            <button className="btn btn-primary" onClick={exitTour}>Exit</button>
          </div>
        </div>
      </div>
    )}

    {chatOpen && <>
      <button className="chat-drawer-scrim" onClick={() => setChatOpen(false)} aria-label="Close Copilot" />
      <aside className="chat-drawer">
        <div className="chat-drawer-head">
          <span>Ask Copilot</span>
          <div className="chat-drawer-head-actions">
            {askForPage(routeView, resolved.scope.clientId === PORTFOLIO) && (
              <button
                className="chat-drawer-ask"
                onClick={() => setQueuedPrompt(
                  askForPage(routeView, resolved.scope.clientId === PORTFOLIO),
                )}
              >
                Ask about this page
              </button>
            )}
            <button className="chat-drawer-close" onClick={() => setChatOpen(false)} aria-label="Close">×</button>
          </div>
        </div>
        <div className="chat-drawer-body">
          <ChatPanel
            scope={resolved.scope}
            queuedPrompt={queuedPrompt}
            queuedScope={queuedScope}
            onQueuedConsumed={() => { setQueuedPrompt(null); setQueuedScope(null); }}
          />
        </div>
      </aside>
    </>}
  </div>;
}
