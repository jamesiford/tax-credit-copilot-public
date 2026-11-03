import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import KpiTile, { KpiRow } from './KpiTile.jsx';

describe('KpiTile', () => {
  it('shows the label, the value and an optional caption', () => {
    render(<KpiTile label="Claimable" value="$805,000" sub="if maintained" />);
    expect(screen.getByText('Claimable')).toBeInTheDocument();
    expect(screen.getByText('$805,000')).toBeInTheDocument();
    expect(screen.getByText('if maintained')).toBeInTheDocument();
  });

  it('is neutral unless it carries a reading, and tones come from the state families', () => {
    const { container, rerender } = render(<KpiTile label="a" value="1" />);
    expect(container.firstChild).toHaveClass('ui-kpi-neutral');
    for (const tone of ['above-min', 'below-min', 'partial', 'base-year']) {
      rerender(<KpiTile label="a" value="1" tone={tone} />);
      expect(container.firstChild).toHaveClass(`ui-kpi-${tone}`);
    }
  });

  it('falls back to neutral for a tone it does not know rather than inventing a colour', () => {
    const { container } = render(<KpiTile label="a" value="1" tone="magenta" />);
    expect(container.firstChild).toHaveClass('ui-kpi-neutral');
  });

  it('lets an absent figure recede instead of competing with a real one', () => {
    const { container } = render(<KpiTile label="Exposure" value="$9" empty />);
    expect(container.firstChild).toHaveClass('ui-kpi-empty');
    expect(screen.getByText('—')).toBeInTheDocument();
    expect(screen.queryByText('$9')).not.toBeInTheDocument();
  });

  it('renders a value it is given verbatim, as a string, so money is not reformatted', () => {
    render(<KpiTile label="Total" value="$1,234,567.89" />);
    expect(screen.getByText('$1,234,567.89')).toBeInTheDocument();
  });
});

describe('KpiRow', () => {
  it('groups tiles under a label', () => {
    render(<KpiRow label="Summary"><KpiTile label="a" value="1" /><KpiTile label="b" value="2" /></KpiRow>);
    expect(screen.getByRole('group', { name: 'Summary' }).children).toHaveLength(2);
  });
});
