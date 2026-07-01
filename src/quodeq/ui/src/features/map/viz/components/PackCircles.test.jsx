import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import PackCircles from './PackCircles.jsx';

// Minimal circles fixture: one folder, one file
const mockCircles = [
  {
    x: 100, y: 100, r: 40, depth: 1,
    data: { path: 'src/', name: 'src', isFile: false, children: [{}], severity: { critical: 0, major: 0, minor: 0 }, violations: 0, compliance: 0, complianceRate: 1 },
  },
  {
    x: 200, y: 200, r: 10, depth: 2,
    data: { path: 'src/foo.js', name: 'foo.js', isFile: true, children: [], severity: { critical: 0, major: 0, minor: 0 }, violations: 0, compliance: 0, complianceRate: 1 },
  },
];

function renderPackCircles(handleClick = vi.fn()) {
  return render(
    <svg>
      <PackCircles
        circles={mockCircles}
        folderIndices={[0]}
        fileIndices={[1]}
        hover={null}
        setHover={vi.fn()}
        viewMode="violations"
        k={1}
        handleClick={handleClick}
      />
    </svg>
  );
}

describe('PackCircles keyboard accessibility (#2056)', () => {
  it('folder circle has tabIndex=0', () => {
    renderPackCircles();
    const circle = document.querySelector('circle');
    expect(circle).toHaveAttribute('tabindex', '0');
  });

  it('folder circle carries the viz-focusable class (suppresses stray focus ring)', () => {
    renderPackCircles();
    const circle = document.querySelector('circle');
    expect(circle).toHaveClass('viz-focusable');
  });

  it('folder circle has role="button"', () => {
    renderPackCircles();
    const circle = document.querySelector('circle');
    expect(circle).toHaveAttribute('role', 'button');
  });

  it('folder circle has aria-label with the node name', () => {
    renderPackCircles();
    const circle = document.querySelector('circle');
    expect(circle).toHaveAttribute('aria-label', 'src');
  });

  it('Enter key on folder circle fires handleClick', () => {
    const handleClick = vi.fn();
    renderPackCircles(handleClick);
    const circle = document.querySelector('circle');
    fireEvent.keyDown(circle, { key: 'Enter' });
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('Space key on folder circle fires handleClick', () => {
    const handleClick = vi.fn();
    renderPackCircles(handleClick);
    const circle = document.querySelector('circle');
    fireEvent.keyDown(circle, { key: ' ' });
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('unrelated key on folder circle does NOT fire handleClick', () => {
    const handleClick = vi.fn();
    renderPackCircles(handleClick);
    const circle = document.querySelector('circle');
    fireEvent.keyDown(circle, { key: 'Tab' });
    expect(handleClick).not.toHaveBeenCalled();
  });
});
