import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import DegradedBanner from './DegradedBanner.jsx';

describe('the degraded banner', () => {
  it('says nothing when everything answered', () => {
    const { container } = render(<DegradedBanner degraded={[]} />);
    expect(container).toBeEmptyDOMElement();
    expect(render(<DegradedBanner />).container).toBeEmptyDOMElement();
  });

  it('names each dependency, what it costs and what to do', () => {
    render(
      <DegradedBanner
        degraded={[
          { dependency: 'claims_store', impact: 'claim figures are unavailable.', remedy: 'Run the migration.' },
          { dependency: 'source_sql', impact: 'the footprint map is empty.', remedy: 'Check the server.' },
        ]}
      />,
    );
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.getByText('2 parts of this page are unavailable')).toBeInTheDocument();
    expect(screen.getByText('claims_store')).toBeInTheDocument();
    expect(screen.getByText(/claim figures are unavailable/)).toBeInTheDocument();
    expect(screen.getByText('Run the migration.')).toBeInTheDocument();
    expect(screen.getByText('source_sql')).toBeInTheDocument();
  });

  it('uses the singular title for one entry', () => {
    render(<DegradedBanner degraded={[{ dependency: 'claims_store', impact: 'x', remedy: 'y' }]} />);
    expect(screen.getByText('Part of this page is unavailable')).toBeInTheDocument();
  });
});
