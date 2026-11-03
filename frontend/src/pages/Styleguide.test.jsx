import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import Styleguide from './Styleguide.jsx';

afterEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute('data-theme');
});

describe('the style guide', () => {
  it('shows every base component', () => {
    render(<Styleguide />);
    for (const name of ['Button', 'Pill', 'CountBadge', 'Tabs', 'KpiTile', 'Card', 'Callout', 'Stepper', 'TaskCard', 'VerdictCard', 'TrailSteps']) {
      expect(screen.getByRole('heading', { name, level: 2 })).toBeInTheDocument();
    }
    expect(screen.getAllByRole('navigation', { name: 'Client review' }).length).toBeGreaterThan(0);
  });

  it('switches the theme and remembers the choice', async () => {
    render(<Styleguide />);
    await userEvent.click(screen.getByRole('tab', { name: 'classic' }));
    expect(document.documentElement.getAttribute('data-theme')).toBe('classic');
    expect(window.localStorage.getItem('tcc-theme')).toBe('classic');
  });
});
