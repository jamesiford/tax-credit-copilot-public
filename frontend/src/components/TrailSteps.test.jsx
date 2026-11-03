import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import TrailSteps from './TrailSteps.jsx';

const STEP = {
  step_id: 'S-01', stage: 'selection', method: 'shared',
  formula: 'rows WHERE pay_date IN window', decision_basis: 'BA-02',
  inputs: { rows: 391000 }, parameters: { window: '2023-07-28..2024-07-31' },
  output: { rows: 384418 }, assumption_ids: ['BA-02'], exceptions: [],
  citation: 'BA-02', calculation_id: 'sha256:1111', code_ref: 'tools/x.py',
  source_hash: 'sha256:aaaaaaaaaaaaaaaaaaaa', config_hash: 'sha256:bbbbbbbbbbbbbbbbbbbb',
  timestamp: '2026-08-26T12:00:00Z',
};

describe('the calculation trail as a stepped list', () => {
  it('is an ordered list of steps, each carrying its formula and citation', () => {
    render(<TrailSteps steps={[STEP, { ...STEP, step_id: 'S-02' }]} />);
    const list = screen.getByRole('list', { name: 'Calculation trail' });
    expect(within(list).getAllByRole('listitem')).toHaveLength(2);
    expect(within(list).getAllByText('rows WHERE pay_date IN window')).toHaveLength(2);
    expect(within(list).getAllByText(/Source: BA-02/)).toHaveLength(2);
  });

  it('shows engine output verbatim, not reworded', () => {
    render(<TrailSteps steps={[STEP]} />);
    expect(screen.getByText(/"rows": 384418/)).toBeInTheDocument();
    expect(screen.getByText(/"window": "2023-07-28..2024-07-31"/)).toBeInTheDocument();
  });

  it('puts a hash chip on the step, with the full hash on hover', () => {
    render(<TrailSteps steps={[STEP]} />);
    const chip = screen.getByTitle('source: sha256:aaaaaaaaaaaaaaaaaaaa');
    expect(chip).toHaveTextContent('source aaaaaaaaaaaa…');
    expect(screen.getByTitle('config: sha256:bbbbbbbbbbbbbbbbbbbb')).toBeInTheDocument();
  });

  it('compact is the printed summary: no inputs, parameters or output', () => {
    render(<TrailSteps steps={[STEP]} compact />);
    expect(screen.getByText('rows WHERE pay_date IN window')).toBeInTheDocument();
    expect(screen.queryByText('Inputs')).toBeNull();
    expect(screen.queryByText(/"rows": 384418/)).toBeNull();
    expect(screen.queryByText('Reproducibility metadata')).toBeNull();
  });

  it('draws nothing for a run with no steps, so the page can say so itself', () => {
    const { container } = render(<TrailSteps steps={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
