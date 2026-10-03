import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, fireEvent, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { fakeCanvasContext } from '../../../../test-utils/fakeCanvasContext.js';
import ZoomablePackView from './ZoomablePackView.jsx';
import { PACK_WORKER_NODE_THRESHOLD } from '../core/packLayout.js';

// Above the threshold the pack paints on one canvas instead of one SVG node
// per circle. Hover and click hit-test the cursor; keyboard users get a
// button per visible child that reaches the same click handler.

function file(i) {
  return { path: `src/f${i}.py`, name: `f${i}.py`, isFile: true, violations: 1, compliance: 0, severity: {} };
}

function bigTree(files = PACK_WORKER_NODE_THRESHOLD) {
  const children = Array.from({ length: files }, (_, i) => file(i));
  const folder = { path: 'src', name: 'src', isFile: false, violations: files, compliance: 0, severity: {}, children };
  return { path: '', name: '/', isFile: false, violations: files, compliance: 0, severity: {}, children: [folder] };
}

const ctx = fakeCanvasContext();

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(ctx);
  ctx.arc.mockClear();
});
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe('ZoomablePackView above the canvas threshold', () => {
  it('renders one canvas and no SVG circles', () => {
    const { container } = render(<ZoomablePackView node={bigTree()} viewMode="health" />);
    expect(container.querySelector('canvas')).toBeInTheDocument();
    expect(container.querySelector('svg')).toBeNull();
    expect(container.querySelectorAll('circle').length).toBe(0);
    expect(ctx.arc).toHaveBeenCalled();
  });

  it('stays on SVG below the threshold', () => {
    const { container } = render(<ZoomablePackView node={bigTree(3)} viewMode="health" />);
    expect(container.querySelector('svg')).toBeInTheDocument();
    expect(container.querySelector('canvas')).toBeNull();
  });

  it('offers a keyboard button per child of the focused folder that drills in', () => {
    const onDrillDown = vi.fn();
    render(<ZoomablePackView node={bigTree()} viewMode="health" onDrillDown={onDrillDown} />);
    const buttons = screen.getAllByRole('button');
    expect(buttons.length).toBe(1);
    fireEvent.keyDown(buttons[0], { key: 'Enter' });
    expect(onDrillDown).toHaveBeenCalledWith('src');
  });

  it('opens a file from the keyboard once drilled into its folder', () => {
    const onFileClick = vi.fn();
    render(<ZoomablePackView node={bigTree()} viewMode="health" currentPath="src" onFileClick={onFileClick} />);
    const buttons = screen.getAllByRole('button');
    expect(buttons.length).toBeGreaterThan(1);
    fireEvent.click(buttons[0]);
    expect(onFileClick).toHaveBeenCalledWith(expect.objectContaining({ isFile: true }));
  });

  it('Escape on the canvas zooms out to the root path', () => {
    const onDrillDown = vi.fn();
    const { container } = render(<ZoomablePackView node={bigTree()} viewMode="health" currentPath="src" onDrillDown={onDrillDown} />);
    fireEvent.keyDown(container.querySelector('canvas'), { key: 'Escape' });
    expect(onDrillDown).toHaveBeenCalledWith('');
  });

  it('names the canvas and makes it focusable', () => {
    const { container } = render(<ZoomablePackView node={bigTree()} viewMode="health" />);
    const canvas = container.querySelector('canvas');
    expect(canvas).toHaveAttribute('aria-label');
    expect(canvas).toHaveAttribute('tabindex', '0');
  });
});
