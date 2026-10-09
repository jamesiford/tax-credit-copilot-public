import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import SectionTabs, { SectionTabPanel } from './SectionTabs.jsx';

const TABS = [{ id: 'a', label: 'Alpha' }, { id: 'b', label: 'Beta', hint: 'the second' }];

describe('SectionTabs', () => {
  it('is a real tablist, with the active tab selected', () => {
    render(<SectionTabs tabs={TABS} active="b" onChange={() => {}} label="Sections" />);
    expect(screen.getByRole('tablist', { name: 'Sections' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Beta' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Alpha' })).toHaveAttribute('aria-selected', 'false');
  });

  it('reports the tab chosen', async () => {
    const onChange = vi.fn();
    render(<SectionTabs tabs={TABS} active="a" onChange={onChange} />);
    await userEvent.click(screen.getByRole('tab', { name: 'Beta' }));
    expect(onChange).toHaveBeenCalledWith('b');
  });
});

describe('SectionTabPanel', () => {
  it('renders only the active panel by default', () => {
    render(<><SectionTabPanel id="a" active="b">first</SectionTabPanel><SectionTabPanel id="b" active="b">second</SectionTabPanel></>);
    expect(screen.queryByText('first')).not.toBeInTheDocument();
    expect(screen.getByText('second')).toBeInTheDocument();
  });

  it('keeps a visited panel mounted but hidden, so returning costs no refetch', () => {
    render(<SectionTabPanel id="a" active="b" keepMounted visited>kept</SectionTabPanel>);
    const panel = document.querySelector('[role=tabpanel]');
    expect(panel).toHaveTextContent('kept');
    expect(panel).toHaveAttribute('hidden');
  });

  it('does not mount a panel nobody has opened', () => {
    render(<SectionTabPanel id="a" active="b" keepMounted visited={false}>never</SectionTabPanel>);
    expect(screen.queryByText('never')).not.toBeInTheDocument();
  });
});
