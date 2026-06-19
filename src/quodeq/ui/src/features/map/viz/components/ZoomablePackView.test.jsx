import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
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
  it('svg container supports Escape to zoom out (has onKeyDown handler)', () => {
    const onDrillDown = vi.fn();
    const { container } = render(
      <ZoomablePackView node={NODE} viewMode="violations" onDrillDown={onDrillDown} />
    );
    // The svg should carry a keydown handler that handles Escape
    const svg = container.querySelector('svg');
    expect(svg).not.toBeNull();
    // Fire Escape — should call onDrillDown (zoom out / reset path)
    fireEvent.keyDown(svg, { key: 'Escape' });
    expect(onDrillDown).toHaveBeenCalled();
  });
});
