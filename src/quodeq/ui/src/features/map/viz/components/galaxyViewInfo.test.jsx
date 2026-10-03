/**
 * Coverage for galaxyViewInfo.jsx: all three navigation depths through
 * computeLevelInfo, the pure per-level compute functions, buildBreadcrumb
 * and the LevelInfoPanel presentational component.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import {
  LevelInfoPanel, computeLevelInfo, buildBreadcrumb, computeDimensionLevelInfo, computePrincipleLevelInfo,
} from './galaxyViewInfo.jsx';

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
    expect(info.lines.some((l) => l.label === 'Score' && l.value === '7.2')).toBe(true);
    expect(info.lines.some((l) => l.label === 'Compliance' && l.value === 6)).toBe(true);
  });

  it('depth 0 averages the score and sums counts across every star', () => {
    const scene = makeScene();
    scene.stars.push({
      name: 'Dim2', score: 5.8, violations: 2, compliance: 3, _clusterCx: 50, _clusterCy: 50,
      _raw: { violations: [{ severity: 'major' }, {}] },
    });
    const nav = { depth: 0, dim: null, prin: null, clusterCx: null, clusterCy: null };
    const info = computeLevelInfo(scene, nav, 'Demo', vi.fn(), { current: nav });
    const value = (label) => info.lines.find((l) => l.label === label)?.value;
    expect(value('Score')).toBe('6.5');
    expect(value('Dimensions')).toBe(2);
    expect(value('Violations')).toBe(6);
    expect(value('Compliance')).toBe(9);
    expect(value('Critical')).toBe(1);
    expect(value('Major')).toBe(2);
    expect(value('Minor')).toBe(2);
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

  it('depth 2 detailAction keeps a genuine rawScore of 0 as the number 0, not "0.0" or null', () => {
    // `p.rawScore || fallback` would treat a real 0 as absent and fall
    // through to `p.score.toFixed(1)` (a string like "5.5"); the fix uses
    // `??` so only null/undefined fall through.
    const scene = makeScene();
    scene.principles[0][0].rawScore = 0;
    const nav = { depth: 2, dim: 0, prin: 0, clusterCx: null, clusterCy: null };
    const onNavigate = vi.fn();
    const navRef = { current: nav };
    const info = computeLevelInfo(scene, nav, 'Demo', onNavigate, navRef);
    info.detailAction();
    expect(onNavigate).toHaveBeenCalledWith('evalprinciple', expect.objectContaining({
      evalPrincipal: expect.objectContaining({ score: 0 }),
    }));
  });

  it('depth 1 returns null instead of throwing when nav.dim is stale after the dimension list shrinks', () => {
    // Drill into dim=1 while the scene has 2 stars.
    const bigScene = makeScene();
    bigScene.stars.push({
      name: 'Dim2', score: 1, violations: 0, compliance: 0, _clusterCx: 60, _clusterCy: 60, _raw: {},
    });
    bigScene.principles.push([{ name: 'P2', score: 1, violations: 0, compliance: 0, critical: 0, major: 0, minor: 0 }]);
    const nav = { depth: 1, dim: 1, prin: null, clusterCx: null, clusterCy: null };
    const navRef = { current: nav };
    expect(computeLevelInfo(bigScene, nav, 'Demo', vi.fn(), navRef).title).toBe('Dim2');

    // A rescan/rescore replaces the scene with a shorter dimension list; nav.dim=1 is now stale.
    const smallScene = makeScene();
    let info;
    expect(() => {
      info = computeLevelInfo(smallScene, nav, 'Demo', vi.fn(), navRef);
    }).not.toThrow();
    expect(info).toBeNull();
  });

  it('depth 2 returns null instead of throwing when nav.prin is stale after the principle list shrinks', () => {
    // Drill into prin=1 while dim=0 has 2 principles.
    const bigScene = makeScene();
    bigScene.principles[0].push({ name: 'P2', score: 2, violations: 0, compliance: 0, critical: 0, major: 0, minor: 0 });
    const nav = { depth: 2, dim: 0, prin: 1, clusterCx: null, clusterCy: null };
    const navRef = { current: nav };
    expect(computeLevelInfo(bigScene, nav, 'Demo', vi.fn(), navRef).title).toBe('P2');

    // A rescan/rescore replaces the scene with a shorter principle list; nav.prin=1 is now stale.
    const smallScene = makeScene();
    let info;
    expect(() => {
      info = computeLevelInfo(smallScene, nav, 'Demo', vi.fn(), navRef);
    }).not.toThrow();
    expect(info).toBeNull();
  });
});

/** True when any value reachable from `value` is a function. */
function containsFunction(value) {
  if (typeof value === 'function') return true;
  if (value && typeof value === 'object') return Object.values(value).some(containsFunction);
  return false;
}

describe('pure level compute functions', () => {
  it('computeDimensionLevelInfo returns a plain Explorer detailTarget', () => {
    const scene = makeScene();
    scene.stars[0]._raw.fromDateLabel = 'Sep 1';
    scene.stars[0]._raw.fromProject = 'demo';
    const info = computeDimensionLevelInfo(scene, { depth: 1, dim: 0, prin: null });
    expect(info.detailAction).toBeUndefined();
    expect(info.detailTarget).toEqual({
      tab: 'explorer',
      payload: { dimension: 'security', runId: 'r1', dateLabel: 'Sep 1', fromProject: 'demo', sourceTab: 'map' },
    });
    expect(containsFunction(info)).toBe(false);
  });

  it('computeDimensionLevelInfo has a null detailTarget when the star has no raw data', () => {
    const scene = makeScene();
    delete scene.stars[0]._raw;
    expect(computeDimensionLevelInfo(scene, { depth: 1, dim: 0, prin: null }).detailTarget).toBeNull();
  });

  it('computePrincipleLevelInfo returns a plain evalPrincipal detailTarget', () => {
    const scene = makeScene();
    const info = computePrincipleLevelInfo(scene, { depth: 2, dim: 0, prin: 0 });
    expect(info.detailAction).toBeUndefined();
    expect(info.detailTarget.tab).toBe('evalprinciple');
    expect(info.detailTarget.payload).toEqual(expect.objectContaining({
      sourceTab: 'map',
      evalPrincipal: expect.objectContaining({ principle: 'P1', score: '5.5', dimension: 'Dim1', runId: 'r1' }),
    }));
    expect(containsFunction(info)).toBe(false);
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
