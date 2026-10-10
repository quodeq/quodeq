import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';

// Spy on the two geometry builders while keeping their real behaviour.
vi.mock('../duelTrendGeometry.js', async (orig) => {
  const mod = await orig();
  return { ...mod, buildTrendGeometry: vi.fn(mod.buildTrendGeometry) };
});
vi.mock('../compareDirectionMap.js', async (orig) => {
  const mod = await orig();
  return { ...mod, buildDirectionMap: vi.fn(mod.buildDirectionMap) };
});

const { buildTrendGeometry } = await import('../duelTrendGeometry.js');
const { buildDirectionMap } = await import('../compareDirectionMap.js');
const { default: CompareDuelTrend } = await import('./CompareDuelTrend.jsx');
const { default: CompareDirectionMap } = await import('./CompareDirectionMap.jsx');

const day = (n) => `2026-09-${String(n).padStart(2, '0')}T00:00:00.000Z`;
const A = [{ dateISO: day(1), value: 6 }, { dateISO: day(9), value: 8 }];
const B = [{ dateISO: day(2), value: 5 }, { dateISO: day(10), value: 5.5 }];

describe('chart geometry is not rebuilt on hover', () => {
  it('CompareDuelTrend: moving over the plot re-renders the readout, not the geometry', () => {
    // No `now` prop: "today" must be pinned per mount, or every render
    // would be a new input and the memo would never hit.
    const { container } = render(<CompareDuelTrend a={A} b={B} aName="Alpha" bName="Beta" />);
    const svg = container.querySelector('svg');
    const before = buildTrendGeometry.mock.calls.length;
    fireEvent.mouseMove(svg, { clientX: 200 });
    fireEvent.mouseMove(svg, { clientX: 260 });
    expect(container.querySelector('.compare-duel-trend__tip')).not.toBeNull();
    expect(buildTrendGeometry.mock.calls.length).toBe(before);
  });

  it('CompareDirectionMap: a new hover target re-renders the map, not the geometry', () => {
    const rows = [
      { id: 'a', name: 'a', score: 8.5, delta: 0.6, totalFiles: 900, stale: false },
      { id: 'b', name: 'b', score: 6.5, delta: -0.4, totalFiles: 100, stale: true },
    ];
    const props = { rows, fleetScore: 7.5, setHover: vi.fn(), onOpenProject: vi.fn() };
    const { rerender } = render(<CompareDirectionMap {...props} hover={null} />);
    const before = buildDirectionMap.mock.calls.length;
    rerender(<CompareDirectionMap {...props} hover="a" />);
    rerender(<CompareDirectionMap {...props} hover="b" />);
    expect(buildDirectionMap.mock.calls.length).toBe(before);
  });
});
