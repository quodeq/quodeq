/**
 * Accessibility tests for the pack circles and the nodeStateText helper.
 * 6574: a circle's fill colour carries the severity/compliance state, so the
 * accessible name has to carry it too (nodeStateText + map.nodeStateAria).
 * 6355: both folder circles and file shapes are role="button" hit targets
 * and must activate on Enter and Space, not click alone.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import PackCircles from './PackCircles.jsx';
import { nodeStateText } from '../core/mapColors.js';

const CLEAN_SEV = { critical: 0, major: 0, minor: 0 };

const mockCircles = [
  {
    x: 100, y: 100, r: 40, depth: 1,
    data: { path: 'src/', name: 'src', isFile: false, children: [{}], severity: { critical: 2, major: 1, minor: 0 }, violations: 3, compliance: 1, complianceRate: 0.25 },
  },
  {
    x: 200, y: 200, r: 10, depth: 2,
    data: { path: 'src/foo.js', name: 'foo.js', isFile: true, children: [], severity: { critical: 0, major: 0, minor: 1 }, violations: 1, compliance: 3, complianceRate: 0.75 },
  },
];

function renderPackCircles(handleClick = vi.fn(), viewMode = 'violations') {
  return render(
    <svg>
      <PackCircles
        circles={mockCircles}
        folderIndices={[0]}
        fileIndices={[1]}
        hover={null}
        setHover={vi.fn()}
        viewMode={viewMode}
        k={1}
        handleClick={handleClick}
      />
    </svg>
  );
}

describe('nodeStateText (6574)', () => {
  it('names the worst severity in violations mode', () => {
    expect(nodeStateText({ severity: { critical: 1, major: 3, minor: 5 } }, 'violations')).toBe('critical violations');
    expect(nodeStateText({ severity: { critical: 0, major: 2, minor: 5 } }, 'violations')).toBe('major violations');
    expect(nodeStateText({ severity: { critical: 0, major: 0, minor: 5 } }, 'violations')).toBe('minor violations');
  });

  it('reports a clean node in violations mode', () => {
    expect(nodeStateText({ severity: CLEAN_SEV }, 'violations')).toBe('no violations');
    expect(nodeStateText({}, 'violations')).toBe('no violations');
  });

  it('reports the rounded compliance percentage in compliance and health modes', () => {
    expect(nodeStateText({ complianceRate: 0.876 }, 'compliance')).toBe('88% compliant');
    expect(nodeStateText({ complianceRate: 1 }, 'health')).toBe('100% compliant');
    expect(nodeStateText({}, 'compliance')).toBe('0% compliant');
  });

  it('falls back to the severity wording for an unknown view mode', () => {
    expect(nodeStateText({ severity: { critical: 0, major: 1, minor: 0 } }, undefined)).toBe('major violations');
  });
});

describe('PackCircles accessible names (6574)', () => {
  it('names the folder circle with its state, not just its name', () => {
    const { container } = renderPackCircles();
    expect(container.querySelector('circle')).toHaveAttribute('aria-label', 'src, critical violations');
  });

  it('names the file shape with its state', () => {
    const { container } = renderPackCircles();
    expect(container.querySelector('path[role="button"]')).toHaveAttribute('aria-label', 'foo.js, minor violations');
  });

  it('switches the state wording with the view mode', () => {
    const { container } = renderPackCircles(vi.fn(), 'compliance');
    expect(container.querySelector('circle')).toHaveAttribute('aria-label', 'src, 25% compliant');
  });
});

describe('PackCircles keyboard activation (6355)', () => {
  it('activates a folder circle on Enter and Space', () => {
    const handleClick = vi.fn();
    const { container } = renderPackCircles(handleClick);
    const circle = container.querySelector('circle');
    fireEvent.keyDown(circle, { key: 'Enter' });
    fireEvent.keyDown(circle, { key: ' ' });
    expect(handleClick).toHaveBeenCalledTimes(2);
  });

  it('makes the file shape a focusable button that activates on Enter and Space', () => {
    const handleClick = vi.fn();
    const { container } = renderPackCircles(handleClick);
    const file = container.querySelector('path[role="button"]');
    expect(file).toHaveAttribute('tabindex', '0');
    fireEvent.keyDown(file, { key: 'Enter' });
    fireEvent.keyDown(file, { key: ' ' });
    expect(handleClick).toHaveBeenCalledTimes(2);
  });

  it('ignores an unrelated key on either shape', () => {
    const handleClick = vi.fn();
    const { container } = renderPackCircles(handleClick);
    fireEvent.keyDown(container.querySelector('circle'), { key: 'Tab' });
    fireEvent.keyDown(container.querySelector('path[role="button"]'), { key: 'Tab' });
    expect(handleClick).not.toHaveBeenCalled();
  });
});
