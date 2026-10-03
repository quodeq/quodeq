import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import ZoomablePackView from './ZoomablePackView.jsx';

const NODE = {
  path: 'root/',
  name: 'root',
  isFile: false,
  violations: 5,
  compliance: 3,
  severity: {},
  children: [
    {
      path: 'root/a/',
      name: 'a',
      isFile: false,
      violations: 2,
      compliance: 1,
      severity: {},
      children: [
        { path: 'root/a/foo.js', name: 'foo.js', isFile: true, violations: 1, compliance: 0, severity: {} },
      ],
    },
  ],
};

describe('ZoomablePackView container Escape key (#1907)', () => {
  it('svg container carries a keydown handler', () => {
    const { container } = render(
      <ZoomablePackView node={NODE} viewMode="violations" onDrillDown={vi.fn()} />
    );
    const svg = container.querySelector('svg');
    expect(svg).not.toBeNull();
  });

  it('Escape zooms out to the root path', () => {
    const onDrillDown = vi.fn();
    const { container } = render(
      <ZoomablePackView node={NODE} viewMode="violations" onDrillDown={onDrillDown} />
    );
    const svg = container.querySelector('svg');
    fireEvent.keyDown(svg, { key: 'Escape' });
    expect(onDrillDown).toHaveBeenCalledWith('');
  });

  it('svg container carries the viz-focusable class (suppresses stray focus ring)', () => {
    const { container } = render(
      <ZoomablePackView node={NODE} viewMode="violations" onDrillDown={vi.fn()} />
    );
    const svg = container.querySelector('svg');
    expect(svg).toHaveClass('viz-focusable');
  });
});

// Labels belong to the children of the focused node. A view-mode switch
// builds a new hierarchy while `focus` still points at a node from the old
// one, so nothing matched until a zoom re-pointed focus into the new tree.
describe('ZoomablePackView focus across layouts', () => {
  const labels = (container) => [...container.querySelectorAll('text')].map((n) => n.textContent);

  it('keeps the focused folder and its labels after a view-mode switch', () => {
    const { container, rerender } = render(
      <ZoomablePackView node={NODE} viewMode="violations" currentPath="root/a/" />
    );
    expect(labels(container)).toEqual(['foo.js']);

    rerender(<ZoomablePackView node={NODE} viewMode="health" currentPath="root/a/" />);
    expect(labels(container)).toEqual(['foo.js']);
  });
});
