import { useState } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { applyTheme, THEME_STORAGE_KEY, THEMES } from '../brand.config.js';
import {
  Button, Callout, Card, CountBadge, EmptyState, FloatingAction, HeroBand, KpiRow, KpiTile,
  MetaLine, Pill, SectionHeading, Skeleton, Stepper, Tabs, TaskCard, VerdictCard,
} from '../components/ui/index.js';
import './Styleguide.css';
import ClientHeader from '../components/ClientHeader.jsx';
import DrillTrail from '../components/shell/DrillTrail.jsx';
import TopBar from '../components/shell/TopBar.jsx';
import StartHereCards from '../components/StartHereCards.jsx';
import TrailSteps from '../components/TrailSteps.jsx';

const TRAIL = [{
  step_id: 'S-01', stage: 'selection', method: 'shared', decision_basis: 'BA-02',
  formula: 'rows WHERE pay_date IN window',
  inputs: { rows: 391000 }, parameters: { window: '2023-07-28..2024-07-31' }, output: { rows: 384418 },
  assumption_ids: ['BA-02'], exceptions: [], citation: 'BA-02',
  source_hash: 'sha256:aaaaaaaaaaaaaaaaaaaa', config_hash: 'sha256:bbbbbbbbbbbbbbbbbbbb',
}];

const NOOP = {
  onOpenPortfolio: () => {}, onOpenClient: () => {}, onOpenUnit: () => {}, onSelectView: () => {},
};
const SHELL_GROUPS = [
  { section: 'What is it worth', items: [
    { id: 'eligibility', label: 'Eligibility', disabled: true, reason: 'Pick a client first' },
    { id: 'onezero', label: 'Monthly employment' },
  ] },
  { section: 'What needs a decision', items: [
    { id: 'ingestion', label: 'Payroll data' }, { id: 'agents', label: 'Agents' },
  ] },
  { section: 'Prove it', items: [{ id: 'evidence', label: 'Audit trail' }, { id: 'rules', label: 'Programs' }] },
];

/**
 * The owner's visual review surface: every `ui/` component in every variant,
 * with a theme toggle. Dev only — `main.jsx` mounts it behind
 * `import.meta.env.DEV`, so it is absent from the production bundle.
 *
 * It renders real components with fixture props and nothing else: no network,
 * no client data. If a component cannot be shown here in all its variants it
 * is not finished.
 */
const STATES = ['above-min', 'below-min', 'base-year', 'partial', 'neutral'];
const TABS = [
  { id: 'who', label: 'Who to call', count: 4 },
  { id: 'all', label: 'Everyone', count: 5 },
  { id: 'off', label: 'Not ready', disabled: true },
];
const STEPS = [
  { id: 'a', label: 'Position', status: 'done', href: '#a' },
  { id: 'b', label: 'Eligibility', status: 'done', href: '#b' },
  { id: 'c', label: 'Trend', status: 'current', href: '#c' },
  { id: 'd', label: 'At risk', status: 'upcoming', href: '#d' },
  { id: 'e', label: 'Evidence', status: 'disabled' },
];

function Section({ title, children }) {
  return (
    <section className="sg-section" aria-labelledby={`sg-${title}`}>
      <h2 id={`sg-${title}`} className="sg-title">{title}</h2>
      <div className="sg-row">{children}</div>
    </section>
  );
}

export default function Styleguide() {
  const [theme, setTheme] = useState(document.documentElement.getAttribute('data-theme') || 'modern');
  const [tab, setTab] = useState('who');
  const [seg, setSeg] = useState('min_max');

  const choose = (next) => {
    window.localStorage.setItem(THEME_STORAGE_KEY, next);
    applyTheme();
    setTheme(next);
  };

  return (
    <main className="sg-page">
      <header className="sg-head">
        <h1 className="sg-h1">Style guide</h1>
        <Tabs
          tabs={THEMES.map((id) => ({ id, label: id }))}
          active={theme}
          onChange={choose}
          label="Theme"
          idPrefix="sg-theme"
          variant="segmented"
          controls={false}
        />
      </header>

      <HeroBand title="Hi, there" aside={<Pill variant="category">Preview</Pill>}>
        Four clients need a call this week; one is a single hire from a threshold.
      </HeroBand>
      <HeroBand compact title="Compact band">A subline of at most one line.</HeroBand>

      <Section title="Button">
        {['primary', 'secondary', 'ghost', 'link', 'danger'].map((v) => <Button key={v} variant={v}>{v}</Button>)}
        <Button variant="primary" size="sm">small</Button>
        <Button variant="primary" loading>loading</Button>
        <Button variant="secondary" disabled>disabled</Button>
      </Section>

      <Section title="Pill">
        {STATES.map((s) => <Pill key={s} variant={s} icon="dot">{s}</Pill>)}
        {STATES.map((s) => <Pill key={`o-${s}`} variant={s} tone="outline" icon="check">{s}</Pill>)}
        <Pill variant="info">info</Pill>
        <Pill variant="category">category</Pill>
        <Pill variant="below-min" icon="x">Not eligible</Pill>
      </Section>

      <Section title="CountBadge">
        <CountBadge count={3} label="open findings" />
        <CountBadge count={351} label="notifications" />
        <CountBadge count={0} showZero label="alerts" />
      </Section>

      <Section title="Tabs">
        <Tabs tabs={TABS} active={tab} onChange={setTab} label="Underline tabs" idPrefix="sg-u" />
        <Tabs
          tabs={[{ id: 'min_max', label: 'Min-Max' }, { id: 'pay_period', label: 'Pay Period' }]}
          active={seg}
          onChange={setSeg}
          label="Segmented tabs"
          idPrefix="sg-s"
          variant="segmented"
          controls={false}
        />
      </Section>

      <Section title="KpiTile">
        <KpiRow label="KPI tiles">
          <KpiTile label="Under review" value="6" />
          <KpiTile label="Qualifies" value="7" tone="above-min" />
          <KpiTile label="Below minimum" value="3" tone="below-min" />
          <KpiTile label="Unverified" value="2" tone="partial" sub="client-asserted" />
          <KpiTile label="Base year" value="TY2021" tone="base-year" />
          <KpiTile label="Exposure" value="$0" empty />
        </KpiRow>
      </Section>

      <Section title="Card">
        <Card title="Portfolio value" subtitle="Identified, not claimed" actions={<Button size="sm">View</Button>}
          tabs={<Tabs tabs={TABS} active={tab} onChange={setTab} label="Card tabs" idPrefix="sg-c" />}
          footer={<span>Total identified: $149k</span>}>
          <p>Body content sits here.</p>
        </Card>
        <Card tone="subtle" title="Subtle card"><p>Used for inset groups.</p></Card>
      </Section>

      <Section title="Callout">
        {['neutral', ...STATES.slice(0, 4)].map((t) => (
          <Callout key={t} title="Eligibility assessment" tone={t}>The derivation sentence states why.</Callout>
        ))}
      </Section>

      <Section title="MetaLine / SectionHeading">
        <MetaLine items={[{ label: 'Client', value: 'Cascade' }, { label: 'Tax year', value: 'TY2023' }, { label: 'Method', value: 'Min-Max' }]} />
        <SectionHeading count={4}>Identified</SectionHeading>
      </Section>

      <Section title="Stepper">
        <Stepper steps={STEPS} label="Client review" />
      </Section>

      <Section title="TaskCard">
        <TaskCard href="#who" title="Who to call" description="Clients ranked by the reason to act." category="Targeting" />
        <TaskCard href="#rules" title="Programs and rules" description="What statute is authored, by year." category="Reference" />
      </Section>

      <Section title="Shell: top bar and drill trail">
        <div className="sg-shell">
          <TopBar groups={SHELL_GROUPS} activeId="onezero" onSelect={() => {}} onHome={() => {}} />
          <DrillTrail clientId="portfolio" view="trend" {...NOOP} />
          <DrillTrail clientId={2001} clientName="Cascade Retail Partners" view="trend" {...NOOP} />
          <DrillTrail clientId={2001} clientName="Cascade Retail Partners" unitId="GA_GA-001" view="trend" {...NOOP} />
          <DrillTrail
            clientId={2001} clientName="Cascade Retail Partners" unitId="GA_GA-001" token="t" view="trend" {...NOOP}
          />
        </div>
      </Section>

      <Section title="Home: hero and task cards">
        <HeroBand compact title="Hi, Jane" aside={<Pill variant="category">Start here</Pill>}>
          Who to target, ranked by the reason to act, not by dollar value.
        </HeroBand>
        <StartHereCards id="sg-start" firstClientId={2001} onNavigate={() => {}} onShowBook={() => {}} />
      </Section>

      <Section title="Card: verdict tones and flush grid">
        <div className="tcc-verdict-grid">
          {['above-min', 'below-min', 'partial', 'base-year'].map((t) => (
            <Card key={t} tone={t} title={`Border: ${t}`}><p>The border encodes the reading, from --state-*.</p></Card>
          ))}
        </div>
        <Card flush title="Flush body" subtitle="A dense grid runs edge to edge">
          <table className="tbl-compact">
            <thead><tr><th>Client</th><th className="num">Identified</th></tr></thead>
            <tbody>
              <tr><td>Cascade</td><td className="num">$149k</td></tr>
              <tr className="row-open"><td>Northwind</td><td className="num">$31k</td></tr>
            </tbody>
          </table>
        </Card>
      </Section>

      <Section title="VerdictCard">
        <div className="tcc-verdict-grid">
          <VerdictCard
            tone="above-min"
            title="Georgia job tax credit"
            pills={[{ variant: 'category', label: 'GA' }, { variant: 'above-min', icon: 'check', label: 'Calculable' }]}
            assessment="Statute is authored for 2019–2025, so each of those years prices under the rules in force that year."
            details={{ onClick: () => {} }}
          >
            <p className="tcc-verdict-text">O.C.G.A. § 48-7-40 · minimum 2 new jobs</p>
          </VerdictCard>
          <VerdictCard
            tone="partial"
            title="Employee counted at two worksites"
            pills={[{ variant: 'category', label: 'E00200' }, { variant: 'partial', icon: 'dot', label: 'Needs a decision' }]}
            assessmentTitle="Why it matters"
            assessment="The engine counts headcount per unit, so a person at two worksites is counted twice."
          />
        </div>
      </Section>

      <Section title="Client review header">
        <MemoryRouter>
          <ClientHeader
            clientId={2001}
            clientName="Cascade Retail Partners"
            industry="Retail"
            year={2023}
            current="location"
            method="min_max"
            run={{ run_id: 'abcdef0123456789', rule_pack_version: 'rules/ga_jtc/2023.json' }}
            onBack={() => {}}
          />
          <ClientHeader
            clientId={9}
            clientName="No payroll yet"
            clientScope={{ payroll_years: [], calculable_years: [] }}
            onBack={() => {}}
          />
        </MemoryRouter>
      </Section>

      <Section title="TrailSteps">
        <TrailSteps steps={TRAIL} />
      </Section>

      <Section title="EmptyState / Skeleton">
        <EmptyState title="Awaiting the next run" action={<Button variant="primary">Run TY2023 now</Button>}>
          Not assessed yet. It carries no figure — not a zero.
        </EmptyState>
        <Skeleton lines={3} />
      </Section>

      <FloatingAction label="Ask" icon="?" onClick={() => {}} />
    </main>
  );
}
