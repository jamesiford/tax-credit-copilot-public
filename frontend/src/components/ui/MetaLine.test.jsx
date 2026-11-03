import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import MetaLine from './MetaLine';

describe('MetaLine', () => {
  it('renders each pair as dt/dd inside a wrapping div', () => {
    const { container } = render(
      <MetaLine
        items={[
          { label: 'Run', value: 'Today' },
          { label: 'Year', value: 'TY2023' },
        ]}
      />,
    );
    const dl = container.querySelector('dl');
    expect(dl).toHaveClass('ui-meta');
    const wrappers = dl.querySelectorAll(':scope > div');
    expect(wrappers).toHaveLength(2);
    expect(wrappers[0].querySelector('dt')).toHaveTextContent('Run');
    expect(wrappers[0].querySelector('dd')).toHaveTextContent('Today');
    expect(screen.getByText('TY2023').tagName).toBe('DD');
  });

  it('keeps the separator and colon out of the DOM text', () => {
    const { container } = render(
      <MetaLine
        items={[
          { label: 'A', value: '1' },
          { label: 'B', value: '2' },
        ]}
      />,
    );
    expect(container.textContent).toBe('A1B2');
  });

  it('skips items whose value is null, undefined or empty', () => {
    const { container } = render(
      <MetaLine
        items={[
          { label: 'Keep', value: 'yes' },
          { label: 'Null', value: null },
          { label: 'Undef', value: undefined },
          { label: 'Empty', value: '' },
        ]}
      />,
    );
    expect(container.querySelectorAll('dt')).toHaveLength(1);
    expect(screen.queryByText('Null')).toBeNull();
  });

  it('keeps zero as a real value', () => {
    render(<MetaLine items={[{ label: 'Jobs', value: 0 }]} />);
    expect(screen.getByText('0').tagName).toBe('DD');
  });

  it('renders nothing when there is nothing to show', () => {
    const { container, rerender } = render(<MetaLine items={[]} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<MetaLine />);
    expect(container).toBeEmptyDOMElement();
    rerender(<MetaLine items={[{ label: 'X', value: null }]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
