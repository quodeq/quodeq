/**
 * Smoke coverage for galaxyViewInfo.jsx, written BEFORE computeLevelInfo is
 * split into computeSystemLevelInfo/computeDimensionLevelInfo/
 * computePrincipleLevelInfo + a shared buildSevLines helper. Exercises all
 * three navigation depths plus buildBreadcrumb and the LevelInfoPanel
 * presentational component.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { LevelInfoPanel, computeLevelInfo, buildBreadcrumb } from './galaxyViewInfo.jsx';

function makeScene() {
  const star = {
    name: 'Dim1', score: 7.2, violations: 4, compliance: 6,
    _clusterCx: 50, _clusterCy: 50,
    _raw: { violations: [{ severity: 'critical' }, { severity: 'major' }, { severity: 'minor' }], fromRunId: 'r1', dimension: 'security' },
  };
  const principle = { name: 'P1', score: 5.5, violations: 2, compliance: 1, critical: 1, major: 0, minor: 1 };
  return {
    stars: [star],
    principles: [[principle]],
    constellations: [{ cx: 50, cy: 50, label: 'Cluster A' }],
  };
}

describe('computeLevelInfo', () => {
  it('returns null with no scene', () => {
    expect(computeLevelInfo(null, { depth: 0, dim: null, prin: null, clusterCx: null, clusterCy: null }, 'Demo', vi.fn(), { current: {} })).toBeNull();
  });

  it('depth 0 (system level) summarizes every star', () => {
    const scene = makeScene();
    const nav = { depth: 0, dim: null, prin: null, clusterCx: null, clusterCy: null };
    const info = computeLevelInfo(scene, nav, 'Demo', vi.fn(), { current: nav });
    expect(info.title).toBe('Demo System');
    expect(info.lines.some((l) => l.label === 'Violations' && l.value === 4)).toBe(true);
    expect(info.lines.some((l) => l.label === 'Critical')).toBe(true);
  });

  it('depth 0 titles from the active cluster when clusterCx/Cy are set', () => {
    const scene = makeScene();
    const nav = { depth: 0, dim: null, prin: null, clusterCx: 50, clusterCy: 50 };
    const info = computeLevelInfo(scene, nav, 'Demo', vi.fn(), { current: nav });
    expect(info.title).toBe('Cluster A');
  });

  it('depth 1 (dimension level) exposes a detailAction that calls onNavigate', () => {
    const scene = makeScene();
    const nav = { depth: 1, dim: 0, prin: null, clusterCx: null, clusterCy: null };
    const onNavigate = vi.fn();
    const navRef = { current: nav };
    const info = computeLevelInfo(scene, nav, 'Demo', onNavigate, navRef);
    expect(info.title).toBe('Dim1');
    info.detailAction();
    expect(onNavigate).toHaveBeenCalledWith('explorer', expect.objectContaining({ dimension: 'security' }));
  });

  it('depth 2 (principle level) exposes a detailAction that calls onNavigate with evalPrincipal', () => {
    const scene = makeScene();
    const nav = { depth: 2, dim: 0, prin: 0, clusterCx: null, clusterCy: null };
    const onNavigate = vi.fn();
    const navRef = { current: nav };
    const info = computeLevelInfo(scene, nav, 'Demo', onNavigate, navRef);
    expect(info.title).toBe('P1');
    info.detailAction();
    expect(onNavigate).toHaveBeenCalledWith('evalprinciple', expect.objectContaining({
      evalPrincipal: expect.objectContaining({ principle: 'P1' }),
    }));
  });
});

describe('buildBreadcrumb', () => {
  it('builds parts for the current nav depth', () => {
    const scene = makeScene();
    const nav = { dim: 0, prin: 0, clusterCx: 50, clusterCy: 50 };
    const parts = buildBreadcrumb(scene, nav, 'Demo');
    expect(parts.map((p) => p.label)).toEqual(['Demo System', 'Cluster A', 'Dim1', 'P1']);
  });
});

describe('LevelInfoPanel', () => {
  it('renders nothing when levelInfo is null', () => {
    const { container } = render(<LevelInfoPanel levelInfo={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders title, lines, and invokes detailAction on click', () => {
    const detailAction = vi.fn();
    render(<LevelInfoPanel levelInfo={{ title: 'Dim1', lines: [{ label: 'Score', value: '7.2' }], hint: 'a hint', detailAction }} />);
    expect(screen.getByText('Dim1')).toBeInTheDocument();
    expect(screen.getByText('a hint')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button'));
    expect(detailAction).toHaveBeenCalled();
  });
});
