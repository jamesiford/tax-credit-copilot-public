import React from 'react';

// Per-agent color cues. Keeps the demo visually parseable as messages stream.
const AGENT_THEMES = {
  OrchestratorAgent:     { dot: 'bg-brand',   text: 'text-brand',   label: 'Orchestrator' },
  PayrollIngestAgent:    { dot: 'bg-accent-2', text: 'text-accent-2', label: 'Payroll Ingest' },
  HeadcountAgent:        { dot: 'bg-success',  text: 'text-success-deep', label: 'Headcount' },
  CreditRulesAgent:      { dot: 'bg-amber-500',       text: 'text-amber-700',       label: 'Credit Rules' },
  CreditDiscoveryAgent:  { dot: 'bg-rose-500',        text: 'text-rose-700',        label: 'Credit Discovery' },
  ClientSituationAgent:  { dot: 'bg-violet-500',      text: 'text-violet-700',      label: 'Client Situation' },
  ExceptionReportAgent:  { dot: 'bg-orange-500',      text: 'text-orange-700',      label: 'Exception Report' },
  RulesIngestionAgent:   { dot: 'bg-teal-500',        text: 'text-teal-700',        label: 'Rules Ingestion' },
  LegislativeMonitorAgent: { dot: 'bg-cyan-600',      text: 'text-cyan-700',        label: 'Legislative Monitor' },
  ReportingAgent:        { dot: 'bg-sky-500',         text: 'text-sky-700',         label: 'Reporting' },
};

/**
 * A readable label for an agent nobody has themed yet.
 *
 * The map used to fall back to the RAW name, so adding a tenth agent put
 * `ClientSituationAgent` on screen beside "Payroll Ingest" and "Reporting".
 * Deriving the label means a new agent is merely unstyled rather than visibly
 * unfinished.
 */
export function humaniseAgent(agent) {
  return String(agent || '')
    .replace(/Agent$/, '')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .trim() || 'Assistant';
}

export default function AgentBadge({ agent, active = false }) {
  const t = AGENT_THEMES[agent] || {
    dot: 'bg-muted', text: 'text-muted', label: humaniseAgent(agent),
  };
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium transition ${
        active
          ? 'border-brand/30 bg-brand/5 ' + t.text
          : 'border-subtle-2 bg-white ' + t.text
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${t.dot} ${active ? 'animate-pulse' : ''}`} />
      {t.label}
    </span>
  );
}
