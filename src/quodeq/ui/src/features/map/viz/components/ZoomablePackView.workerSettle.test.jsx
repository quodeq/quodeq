import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, act } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { fakeCanvasContext } from '../../../../test-utils/fakeCanvasContext.js';
import ZoomablePackView from './ZoomablePackView.jsx';
import { PACK_WORKER_NODE_THRESHOLD, buildPackRoot, slimTree, packSlim } from '../core/packLayout.js';

// Large trees lay out in the worker. The first Map visit renders before the
// reply, so the view must pick up the positions when they land: the focus
// transform is derived from the root's radius, which does not exist yet at
// first render.

let resolveReply;
vi.mock('../core/packWorkerClient.js', () => ({
  requestPackLayout: () => new Promise((resolve) => { resolveReply = resolve; }),
  resetPackWorker: () => {},
}));

function file(i) {
  return { path: `src/f${i}.py`, name: `f${i}.py`, isFile: true, violations: 1, compliance: 0, severity: {} };
}

function bigTree() {
  const children = Array.from({ length: PACK_WORKER_NODE_THRESHOLD }, (_, i) => file(i));
  const folder = { path: 'src', name: 'src', isFile: false, violations: children.length, compliance: 0, severity: {}, children };
  return { path: '', name: '/', isFile: false, violations: children.length, compliance: 0, severity: {}, children: [folder] };
}

const ctx = fakeCanvasContext();

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(ctx);
  ctx.arc.mockClear();
});
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe('ZoomablePackView when the worker reply lands after first render', () => {
  it('draws every circle at finite coordinates once the layout settles', async () => {
    const tree = bigTree();
    const { container } = render(<ZoomablePackView node={tree} viewMode="health" />);
    expect(container.querySelector('canvas')).toBeNull();

    const xyr = packSlim(slimTree(buildPackRoot(tree, 'health')));
    await act(async () => { resolveReply(xyr); });

    expect(container.querySelector('canvas')).toBeInTheDocument();
    // Folders are arcs, files are translated icons; every placement is finite.
    expect(ctx.arc).toHaveBeenCalled();
    expect(ctx.translate).toHaveBeenCalled();
    const placements = [...ctx.arc.mock.calls, ...ctx.translate.mock.calls];
    for (const call of placements) {
      expect(Number.isFinite(call[0])).toBe(true);
      expect(Number.isFinite(call[1])).toBe(true);
    }
  });

  it('fades the circles in when the layout lands and again on a view-mode switch', async () => {
    const tree = bigTree();
    const { container, rerender } = render(<ZoomablePackView node={tree} viewMode="health" />);
    const fade = container.querySelector('.pack-fade');
    expect(fade).toHaveAttribute('data-fade', 'a');
    await act(async () => { resolveReply(packSlim(slimTree(buildPackRoot(tree, 'health')))); });
    expect(container.querySelector('.pack-fade')).toBe(fade);
    expect(fade).toHaveAttribute('data-fade', 'b');

    rerender(<ZoomablePackView node={tree} viewMode="violations" />);
    await act(async () => { resolveReply(packSlim(slimTree(buildPackRoot(tree, 'violations')))); });
    expect(container.querySelector('.pack-fade')).toBe(fade);
    expect(fade).toHaveAttribute('data-fade', 'a');
  });

  // The focus transform is rebuilt when the real root replaces the pending
  // placeholder; its values do not change, so the canvas must still treat
  // the zoom as settled and draw labels right away.
  it('draws labels as soon as the layout lands', async () => {
    const tree = bigTree();
    render(<ZoomablePackView node={tree} viewMode="health" showLabels />);
    ctx.fillText.mockClear();
    await act(async () => { resolveReply(packSlim(slimTree(buildPackRoot(tree, 'health')))); });
    expect(ctx.fillText).toHaveBeenCalled();
  });
});
