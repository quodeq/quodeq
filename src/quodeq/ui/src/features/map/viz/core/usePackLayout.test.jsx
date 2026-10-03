import { describe, it, expect, vi } from 'vitest';
import { render, act } from '@testing-library/react';
import { usePackLayout } from './usePackLayout.js';

vi.mock('./layoutCache.js', () => ({ resolvePackLayout: vi.fn() }));
import { resolvePackLayout } from './layoutCache.js';

function Probe({ node, mode }) {
  const { circles } = usePackLayout(node, mode);
  return <output>{circles.length}</output>;
}

const layoutOf = (n) => ({ root: {}, circles: Array.from({ length: n }), pending: false });

describe('usePackLayout', () => {
  it('shows no circles until the worker settles, then the finished layout', async () => {
    let resolve;
    const promise = new Promise((r) => { resolve = r; });
    resolvePackLayout.mockReturnValue({ root: {}, circles: [], pending: true, promise });
    const node = {};
    const { container } = render(<Probe node={node} mode="health" />);
    expect(container.textContent).toBe('0');
    await act(async () => { resolve(layoutOf(5)); await promise; });
    expect(container.textContent).toBe('5');
  });

  it('ignores a reply for a node the view has left', async () => {
    let resolveOld;
    const old = new Promise((r) => { resolveOld = r; });
    resolvePackLayout.mockReturnValueOnce({ root: {}, circles: [], pending: true, promise: old });
    const { container, rerender } = render(<Probe node={{}} mode="health" />);
    resolvePackLayout.mockReturnValueOnce(layoutOf(2));
    rerender(<Probe node={{}} mode="health" />);
    expect(container.textContent).toBe('2');
    await act(async () => { resolveOld(layoutOf(9)); await old; });
    expect(container.textContent).toBe('2');
  });
});
