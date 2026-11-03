import Pill from './ui/Pill.jsx';

//: Plain-language names for the agents we know. Colour does NOT identify an
//: agent any more: a hue per agent was the one place a reading colour carried
//: no reading, and the name is what a reader needs.
const LABELS = {
  OrchestratorAgent: 'Orchestrator',
  PayrollIngestAgent: 'Payroll Ingest',
  HeadcountAgent: 'Headcount',
  CreditRulesAgent: 'Credit Rules',
  CreditDiscoveryAgent: 'Credit Discovery',
  ClientSituationAgent: 'Client Situation',
  ExceptionReportAgent: 'Exception Report',
  RulesIngestionAgent: 'Rules Ingestion',
  LegislativeMonitorAgent: 'Legislative Monitor',
  ReportingAgent: 'Reporting',
};

/**
 * A readable label for an agent nobody has named yet.
 *
 * The map used to fall back to the RAW name, so adding a tenth agent put
 * `ClientSituationAgent` on screen beside "Payroll Ingest" and "Reporting".
 * Deriving the label means a new agent is merely unlisted rather than visibly
 * unfinished.
 */
export function humaniseAgent(agent) {
  return String(agent || '')
    .replace(/Agent$/, '')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .trim() || 'Assistant';
}

/** Which agent spoke, as a small category pill. `active` pulses while it streams. */
export default function AgentBadge({ agent, active = false }) {
  return (
    <Pill variant="category" className={active ? 'ask-agent ask-agent-active' : 'ask-agent'}>
      <span className="ask-agent-dot" aria-hidden="true" />
      {LABELS[agent] || humaniseAgent(agent)}
      {active ? <span className="sr-only"> (working)</span> : null}
    </Pill>
  );
}
