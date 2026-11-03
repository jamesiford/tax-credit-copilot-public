import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import Tabs from './Tabs.jsx';

const TABS = [
  { id: 'a', label: 'Alpha', count: 4 },
  { id: 'b', label: 'Beta', hint: 'the second' },
  { id: 'c', label: 'Gamma', disabled: true },
  { id: 'd', label: 'Delta', count: 0 },
];

function Harness({ initial = 'a', ...props }) {
  const [active, setActive] = useState(initial);
  return <Tabs tabs={TABS} active={active} onChange={setActive} {...props} />;
}

describe('Tabs', () => {
  it('is a labelled tablist with the active tab selected', () => {
    render(<Tabs tabs={TABS} active="b" onChange={() => {}} label="Sections" />);
    expect(screen.getByRole('tablist', { name: 'Sections' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Beta' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: /Alpha/ })).toHaveAttribute('aria-selected', 'false');
  });

  it('shows the count inside the tab, including a zero', () => {
    render(<Tabs tabs={TABS} active="a" onChange={() => {}} />);
    expect(screen.getByRole('tab', { name: /Alpha\s*4/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Delta\s*0/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Beta' }).querySelector('.ui-tab-count')).toBeNull();
  });

  it('reports the tab chosen and exposes the hint as a title', async () => {
    const onChange = vi.fn();
    render(<Tabs tabs={TABS} active="a" onChange={onChange} />);
    await userEvent.click(screen.getByRole('tab', { name: 'Beta' }));
    expect(onChange).toHaveBeenCalledWith('b');
    expect(screen.getByRole('tab', { name: 'Beta' })).toHaveAttribute('title', 'the second');
  });

  it('gives the whole list ONE tab stop (roving tabindex)', () => {
    render(<Tabs tabs={TABS} active="b" onChange={() => {}} />);
    const stops = screen.getAllByRole('tab').filter((tab) => tab.tabIndex === 0);
    expect(stops).toHaveLength(1);
    expect(stops[0]).toHaveTextContent('Beta');
  });

  it('moves with the arrow keys, skips a disabled tab, wraps, and supports Home and End', async () => {
    render(<Harness initial="b" />);
    screen.getByRole('tab', { name: 'Beta' }).focus();
    await userEvent.keyboard('{ArrowRight}');
    expect(screen.getByRole('tab', { name: /Delta/ })).toHaveAttribute('aria-selected', 'true');
    await userEvent.keyboard('{ArrowRight}');
    expect(screen.getByRole('tab', { name: /Alpha/ })).toHaveAttribute('aria-selected', 'true');
    await userEvent.keyboard('{ArrowLeft}');
    expect(screen.getByRole('tab', { name: /Delta/ })).toHaveAttribute('aria-selected', 'true');
    await userEvent.keyboard('{Home}');
    expect(screen.getByRole('tab', { name: /Alpha/ })).toHaveAttribute('aria-selected', 'true');
    await userEvent.keyboard('{End}');
    expect(screen.getByRole('tab', { name: /Delta/ })).toHaveAttribute('aria-selected', 'true');
  });

  it('never activates a disabled tab', async () => {
    const onChange = vi.fn();
    render(<Tabs tabs={TABS} active="a" onChange={onChange} />);
    await userEvent.click(screen.getByRole('tab', { name: 'Gamma' }));
    expect(onChange).not.toHaveBeenCalled();
  });

  it('associates each tab with its panel, unless there are no panels', () => {
    const { rerender } = render(<Tabs tabs={TABS} active="a" onChange={() => {}} idPrefix="grid" />);
    expect(screen.getByRole('tab', { name: 'Beta' })).toHaveAttribute('aria-controls', 'grid-panel-b');
    expect(screen.getByRole('tab', { name: 'Beta' })).toHaveAttribute('id', 'grid-tab-b');
    rerender(<Tabs tabs={TABS} active="a" onChange={() => {}} controls={false} />);
    expect(screen.getByRole('tab', { name: 'Beta' })).not.toHaveAttribute('aria-controls');
  });

  it('takes the segmented variant for an inline choice', () => {
    render(<Tabs tabs={TABS} active="a" onChange={() => {}} variant="segmented" />);
    expect(screen.getByRole('tablist')).toHaveClass('ui-tabs-segmented');
  });

  it('keeps a tab stop even when nothing is active', () => {
    render(<Tabs tabs={TABS} active={null} onChange={() => {}} />);
    expect(screen.getByRole('tab', { name: /Alpha/ }).tabIndex).toBe(0);
  });
});
