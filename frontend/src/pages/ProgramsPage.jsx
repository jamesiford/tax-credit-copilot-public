/*
 * Why: the Program manager sits beside the rule library. `/programs` is the catalog and the drafts; `/programs/<code>` is one
 * program; `/programs/new` starts a draft and `/programs/draft/<id>` continues one. The route says which, so a link points at the
 * exact state. The catalog is read once here and shared with the workflow's first step.
 * Never: compute a figure or say a program is verified: it reports what the registry and the packs hold.
 */
import { useCallback, useEffect, useState } from 'react';
import { PackagePlus } from 'lucide-react';
import { fetchPrograms } from '../api.js';
import AddProgramWorkflow from '../components/programs/AddProgramWorkflow.jsx';
import DraftList from '../components/programs/DraftList.jsx';
import ProgramCatalog from '../components/programs/ProgramCatalog.jsx';
import ProgramDetail from '../components/programs/ProgramDetail.jsx';
import UnverifiedNotice from '../components/programs/UnverifiedNotice.jsx';
import PageHeader from '../components/PageHeader.jsx';
import Button from '../components/ui/Button.jsx';
import EmptyState from '../components/ui/EmptyState.jsx';
import KpiTile, { KpiRow } from '../components/ui/KpiTile.jsx';
import Skeleton from '../components/ui/Skeleton.jsx';
import Tabs from '../components/ui/Tabs.jsx';
import '../components/programs/programs.css';

function useCatalog() {
  const [state, setState] = useState({ loading: true, data: null, error: null });
  useEffect(() => {
    let cancelled = false;
    fetchPrograms()
      .then((data) => { if (!cancelled) setState({ loading: false, data, error: null }); })
      .catch((error) => { if (!cancelled) setState({ loading: false, data: null, error }); });
    return () => { cancelled = true; };
  }, []);
  return state;
}

function Home({ catalog, onOpen, onOpenDraft, onNew }) {
  const [tab, setTab] = useState('catalog');
  const rows = catalog.data?.programs || [];
  const calculable = rows.filter((r) => r.calculable).length;
  return (
    <>
      <PageHeader
        eyebrow="Prove it" title="Program manager"
        sub="What the platform knows, what it can calculate and why not, and how to bring on a new program"
        actions={<Button variant="primary" icon={<PackagePlus size={16} />} onClick={onNew}>Add a program</Button>}
      />
      <UnverifiedNotice />
      <KpiRow label="Program summary">
        <KpiTile label="Registered" value={catalog.data ? rows.length : '\u2014'} />
        <KpiTile label="Calculable" value={catalog.data ? calculable : '\u2014'} sub="for their authored years" />
        <KpiTile label="Described only" value={catalog.data ? rows.filter((r) => r.lifecycle === 'described').length : '\u2014'} sub="no authored year yet" />
      </KpiRow>
      <Tabs
        label="Program manager" idPrefix="prog" active={tab} onChange={setTab}
        tabs={[{ id: 'catalog', label: 'Catalog' }, { id: 'drafts', label: 'Drafts' }]}
      />
      <div role="tabpanel" id={`prog-panel-${tab}`} aria-labelledby={`prog-tab-${tab}`}>
        {tab === 'catalog' && (catalog.loading ? <Skeleton lines={5} label="Reading the catalog" /> : catalog.error ? (
          <EmptyState title="The program catalog is unavailable">{catalog.error.message} Nothing was changed; reload the page to try again.</EmptyState>
        ) : <ProgramCatalog rows={rows} onOpen={onOpen} />)}
        {tab === 'drafts' && <DraftList onOpen={onOpenDraft} onNew={onNew} />}
      </div>
    </>
  );
}

/** `route` is the path after `/programs`: `[]`, `['new']`, `['draft', id]` or `[code]`. */
export default function ProgramsPage({ route = [], navigate }) {
  const catalog = useCatalog();
  const go = useCallback((tail = '') => navigate(`/programs${tail}`), [navigate]);
  const [head, id] = route;
  if (head === 'new' || head === 'draft') {
    return (
      <AddProgramWorkflow
        key={id || 'new'} draftId={head === 'draft' ? id : null} catalog={catalog.data?.programs || []}
        onCreated={(draftId) => go(`/draft/${encodeURIComponent(draftId)}`)} onExit={() => go()}
      />
    );
  }
  if (head) return <ProgramDetail code={decodeURIComponent(head)} onBack={() => go()} />;
  return (
    <Home
      catalog={catalog} onOpen={(code) => go(`/${encodeURIComponent(code)}`)} onNew={() => go('/new')}
      onOpenDraft={(draftId) => go(`/draft/${encodeURIComponent(draftId)}`)}
    />
  );
}
