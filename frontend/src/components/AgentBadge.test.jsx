import { describe, expect, it } from 'vitest';
import { humaniseAgent } from './AgentBadge.jsx';

describe('agent labels', () => {
  it('derives a readable label for an agent nobody has themed', () => {
    // The map used to fall back to the RAW name, so adding a tenth agent put
    // `ClientSituationAgent` on screen beside "Payroll Ingest" and "Reporting".
    expect(humaniseAgent('ClientSituationAgent')).toBe('Client Situation');
    expect(humaniseAgent('ExceptionReportAgent')).toBe('Exception Report');
  });

  it('never renders an empty badge', () => {
    expect(humaniseAgent(undefined)).toBe('Assistant');
    expect(humaniseAgent('')).toBe('Assistant');
    expect(humaniseAgent('Agent')).toBe('Assistant');
  });
});
