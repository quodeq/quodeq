import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import VirtualList from './VirtualList.jsx';

describe('VirtualList fallback path list semantics', () => {
  it('renders a list with one listitem per item when there is no scroll container', () => {
    const items = ['a', 'b', 'c'];
    render(
      <VirtualList
        items={items}
        scrollElement={null}
        estimateSize={() => 40}
        getItemKey={(i) => items[i]}
        renderItem={(item) => <span>{item}</span>}
      />,
    );
    expect(screen.getByRole('list')).toBeInTheDocument();
    expect(screen.getAllByRole('listitem')).toHaveLength(items.length);
  });
});
