import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import VerdictCard from './VerdictCard.jsx';

const draw = (props) => render(
  <MemoryRouter><VerdictCard title="GA job tax credit" {...props}>Body text</VerdictCard></MemoryRouter>,
);

describe('VerdictCard', () => {
  it('is an article named for its title, with the verdict in the border', () => {
    draw({ tone: 'above-min' });
    const card = screen.getByRole('article', { name: 'GA job tax credit' });
    expect(card).toHaveClass('ui-card-verdict-above-min');
  });

  it.each([
    ['above-min', 'check'], ['below-min', 'x'], ['partial', 'dot'],
  ])('states a %s verdict in words and a glyph, not by colour alone', (variant, icon) => {
    draw({ tone: variant, pills: [{ variant: 'category', label: 'GA' }, { variant, icon, label: 'Verdict' }] });
    const pills = document.querySelectorAll('.ui-pill');
    expect(pills).toHaveLength(2);
    expect(pills[1]).toHaveTextContent('Verdict');
    expect(pills[1].querySelector('.ui-pill-icon')).not.toBeNull();
    expect(pills[1]).toHaveClass(`ui-pill-${variant}`);
  });

  it('puts the derivation in an inset callout, and omits it when there is none', () => {
    const { unmount } = draw({ assessment: 'Statute is authored for 2019–2025.' });
    expect(within(screen.getByRole('complementary')).getByText(/authored for 2019/)).toBeInTheDocument();
    unmount();
    draw({});
    expect(screen.queryByRole('complementary')).toBeNull();
  });

  it('never takes a free colour: an unknown tone is neutral', () => {
    draw({ tone: 'brand' });
    expect(screen.getByRole('article')).not.toHaveClass('ui-card-verdict');
  });

  it('links to the drill with a router link, or calls back', async () => {
    const onClick = vi.fn();
    const { unmount } = draw({ details: { to: '/c/2001/evidence' } });
    expect(screen.getByRole('link', { name: /Details/ })).toHaveAttribute('href', '/c/2001/evidence');
    unmount();
    draw({ details: { label: 'Open', onClick } });
    await userEvent.click(screen.getByRole('button', { name: /Open/ }));
    expect(onClick).toHaveBeenCalled();
  });

  it('shows no link when it has nowhere to send you', () => {
    draw({ details: {} });
    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.queryByRole('button')).toBeNull();
  });
});
