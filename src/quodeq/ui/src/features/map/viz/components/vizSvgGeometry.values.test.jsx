/**
 * Value-level characterization for the SVG geometry of FileShape,
 * RiskMatrixView and ZoomablePackView: the file-icon path coordinates and
 * opacities, the risk matrix's plot box, gridlines, axis labels, bubble
 * radii, critical ring radii, label font sizes and tooltip offsets, and the
 * pack view's label thresholds and tooltip clamp margins.
 *
 * Snapshotting the rendered markup is the cheapest way to catch a typo in
 * any of those numbers, because every one of them ends up in an attribute.
 *
 * Captured from the pre-naming code — keep the snapshots unchanged.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, fireEvent, act } from '@testing-library/react';
import FileShape from './FileShape.jsx';
import RiskMatrixView from './RiskMatrixView.jsx';
import ZoomablePackView from './ZoomablePackView.jsx';

const NODE = {
  path: 'root/', name: 'root', isFile: false, violations: 0, compliance: 0, severity: {},
  children: [
    {
      path: 'root/a/', name: 'alpha', isFile: false, violations: 6, compliance: 2,
      severity: { critical: 2, major: 1, minor: 3 },
      children: [{ path: 'root/a/x.js', name: 'x.js', isFile: true, violations: 1, compliance: 0, severity: { minor: 1 } }],
    },
    {
      path: 'root/b.js', name: 'b.js', isFile: true, violations: 1, compliance: 4,
      severity: { critical: 0, major: 1, minor: 0 }, children: [],
    },
    {
      path: 'root/c.js', name: 'c.js', isFile: true, violations: 0, compliance: 9,
      severity: {}, children: [],
    },
  ],
};

describe('FileShape geometry', () => {
  it('draws the body, fold and rule lines at the recorded unit coordinates', () => {
    const { container } = render(
      <FileShape cx={40} cy={25} r={9} color="#abc" borderColor="#def" />,
    );
    expect(container.innerHTML).toMatchSnapshot('file-shape-markup');
  });

  it('compensates the stroke widths for the parent scale', () => {
    const { container } = render(
      <FileShape cx={0} cy={0} r={5} color="#abc" borderColor="#def" parentScale={4}
        glow handlers={{ onClick: () => {} }} ariaLabel="x.js" />,
    );
    expect(container.innerHTML).toMatchSnapshot('file-shape-scaled-markup');
  });
});

describe('RiskMatrixView geometry', () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  function renderEntered(props) {
    const out = render(<RiskMatrixView node={NODE} {...props} />);
    act(() => { vi.runAllTimers(); });
    return out;
  }

  it('lays out the plot box, gridlines, axis labels and bubbles', () => {
    const { container } = renderEntered();
    expect(container.innerHTML).toMatchSnapshot('risk-matrix-markup');
  });

  it('drops the bubble labels when they are turned off', () => {
    const { container } = renderEntered({ showLabels: false });
    expect(container.querySelectorAll('text[text-anchor="middle"]').length)
      .toMatchSnapshot('risk-matrix-label-count-without-labels');
  });

  it('offsets the tooltip from the cursor and flips it past the viewport thresholds', () => {
    const { container } = renderEntered();
    const bubble = container.querySelector('circle.viz-focusable');
    fireEvent.mouseEnter(bubble, { clientX: 100, clientY: 120 });
    expect(container.querySelector('.map-tooltip').getAttribute('style'))
      .toMatchSnapshot('risk-matrix-tooltip-style-near-origin');
    fireEvent.mouseMove(bubble, { clientX: window.innerWidth - 20, clientY: window.innerHeight - 20 });
    expect(container.querySelector('.map-tooltip').getAttribute('style'))
      .toMatchSnapshot('risk-matrix-tooltip-style-flipped');
  });
});

describe('ZoomablePackView geometry', () => {
  it('sizes the viewBox, padding and pack layout from the recorded constants', () => {
    const { container } = render(
      <ZoomablePackView node={NODE} viewMode="violations" onDrillDown={vi.fn()} />,
    );
    expect(container.querySelector('svg').getAttribute('viewBox'))
      .toMatchSnapshot('pack-view-viewbox');
    expect(container.innerHTML).toMatchSnapshot('pack-view-markup');
  });

  it('clamps the tooltip inside the container margins', () => {
    const { container } = render(
      <ZoomablePackView node={NODE} viewMode="violations" onDrillDown={vi.fn()} />,
    );
    const circle = container.querySelectorAll('circle')[1];
    fireEvent.mouseOver(circle);
    fireEvent.mouseEnter(circle);
    const tip = container.querySelector('.map-tooltip');
    expect(tip && tip.getAttribute('style')).toMatchSnapshot('pack-view-tooltip-style');
    // Past the container edge the tooltip clamps to the right/bottom margins
    // measured off the fallback container size.
    fireEvent.mouseMove(container.firstChild, { clientX: 1000, clientY: 1000 });
    fireEvent.mouseOut(circle);
    fireEvent.mouseOver(circle);
    expect(container.querySelector('.map-tooltip').getAttribute('style'))
      .toMatchSnapshot('pack-view-tooltip-style-clamped');
  });
});
