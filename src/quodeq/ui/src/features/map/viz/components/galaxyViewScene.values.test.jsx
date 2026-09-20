/**
 * Value-level characterization for galaxyViewScene and galaxyViewLayout: the
 * star/principle radii, orbit distances, dim-particle ranges, cluster spread
 * and background-star ranges the scene builders bake in, plus the layout
 * module's cluster placement, repulsion gap and extent margins.
 *
 * scoreRGB reads theme colours through a 1x1 canvas, which JSDOM does not
 * implement (vitest.setup.js stubs getContext to null); a minimal 2D context
 * is stubbed here, and Math.random (mkParticles) is made deterministic.
 *
 * Captured from the pre-naming code — keep the snapshots unchanged.
 */
import { describe, it, expect, vi, beforeAll, afterAll, beforeEach, afterEach } from 'vitest';
import { buildScene, computePrincipleScore, updateSceneLiveData } from './galaxyViewScene.js';
import {
  computeClusterPositions, applyRepulsionAndRecenter, computeMaxExtent,
} from './galaxyViewLayout.js';

let originalGetContext;
beforeAll(() => {
  originalGetContext = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function stubGetContext() {
    return {
      clearRect: () => {}, fillRect: () => {}, fillStyle: '',
      getImageData: () => ({ data: [128, 128, 128, 255] }),
    };
  };
});
afterAll(() => { HTMLCanvasElement.prototype.getContext = originalGetContext; });

const round = (n) => (typeof n === 'number' ? Number(n.toFixed(6)) : n);

function mkDim(name, type) {
  return {
    dimension: name,
    overallScore: 7.5,
    _type: type,
    violations: [
      { principle: 'P1', severity: 'critical', file: 'a.js' },
      { principle: 'P1', severity: 'major', file: 'b.js' },
      { principle: 'P2', severity: 'minor', file: 'a.js' },
    ],
    compliance: [{ principle: 'P1' }, { principle: 'P2' }, { principle: 'P2' }],
    principles: [{ name: 'P1', grade: 'B', score: 8 }],
  };
}

const STANDARD_TYPES = { clean: 'builtin', solid: 'builtin', secure: 'community' };

describe('galaxyViewScene value characterization', () => {
  let randomSpy;
  beforeEach(() => {
    let i = 0;
    randomSpy = vi.spyOn(Math, 'random').mockImplementation(() => ((i++ * 7) % 11) / 11);
  });
  afterEach(() => { randomSpy.mockRestore(); });

  it('buildScene places constellation stars at the recorded spread and offsets', () => {
    const scene = buildScene(
      [mkDim('clean'), mkDim('solid'), mkDim('secure')], 800, 600, STANDARD_TYPES,
    );
    expect(scene.stars.map((s) => ({
      name: s.name, radius: round(s.radius), score: round(s.score),
      _clusterCx: round(s._clusterCx), _clusterCy: round(s._clusterCy),
      _ox: round(s._ox), _oy: round(s._oy), ba: round(s.ba), j: round(s.j), pp: round(s.pp),
    }))).toMatchSnapshot('constellation-star-geometry');
    expect(scene.constellations.map((c) => ({
      type: c.type, cx: round(c.cx), cy: round(c.cy), spread: round(c.spread), lines: c.lines,
    }))).toMatchSnapshot('constellation-geometry');
    expect(round(scene._maxExtent)).toMatchSnapshot('constellation-max-extent');
  });

  it('buildScene falls back to the circular single-group layout', () => {
    const scene = buildScene([mkDim('clean'), mkDim('solid')], 800, 600, {});
    expect(scene.stars.map((s) => ({
      name: s.name, radius: round(s.radius), ba: round(s.ba), j: round(s.j), pp: round(s.pp),
    }))).toMatchSnapshot('single-group-star-geometry');
    expect(scene.constellations).toEqual([]);
  });

  it('buildPrinciples derives radius, orbit distance and dim-particle ranges', () => {
    const scene = buildScene([mkDim('clean')], 800, 600, {});
    expect(scene.principles[0].map((p) => ({
      name: p.name, score: round(p.score), radius: round(p.radius),
      ba: round(p.ba), od: round(p.od), pp: round(p.pp),
      particleCount: p.particles.length,
      dimParticle: {
        or: round(p.dimParticle.or), os: round(p.dimParticle.os), op: round(p.dimParticle.op),
        sz: round(p.dimParticle.sz), ec: round(p.dimParticle.ec), tp: round(p.dimParticle.tp),
      },
    }))).toMatchSnapshot('principle-geometry');
  });

  it('buildBackgroundStars keeps the recorded count, size and speed ranges', () => {
    const scene = buildScene([mkDim('clean')], 800, 600, {});
    expect(scene.bg).toHaveLength(120);
    expect(scene.bg.slice(0, 4).map((s) => ({
      x: round(s.x), y: round(s.y), sz: round(s.sz), tw: round(s.tw), sp: round(s.sp),
    }))).toMatchSnapshot('background-star-values');
    const sizes = scene.bg.map((s) => s.sz);
    const speeds = scene.bg.map((s) => s.sp);
    expect(Math.max(...sizes)).toBeLessThanOrEqual(1.2);
    expect(Math.min(...speeds)).toBeGreaterThanOrEqual(0.3);
    expect(Math.max(...speeds)).toBeLessThanOrEqual(1);
  });

  it('computePrincipleScore scales the compliance ratio and keeps the neutral default', () => {
    expect(computePrincipleScore(null, null, 1, 3)).toBeCloseTo(7.5);
    expect(computePrincipleScore(null, null, 0, 0)).toBe(5);
    expect(computePrincipleScore(null, 'C', 0, 0)).toBe(6.5);
  });

  it('updateSceneLiveData recomputes scores without moving the layout', () => {
    const scene = buildScene([mkDim('clean')], 800, 600, {});
    const before = scene.stars.map((s) => ({ ox: s._ox, oy: s._oy, radius: s.radius }));
    updateSceneLiveData(scene, [{ dimension: 'clean', overallScore: 'nope', violations: [], compliance: [], principles: [] }]);
    expect(scene.stars[0].score).toBe(5);
    expect(scene.stars.map((s) => ({ ox: s._ox, oy: s._oy, radius: s.radius }))).toEqual(before);
  });
});

describe('galaxyViewLayout value characterization', () => {
  it('computeClusterPositions seeds distances inside the recorded range', () => {
    expect(computeClusterPositions(['builtin'])).toEqual([[0, 0]]);
    expect(computeClusterPositions(['builtin', 'quodeq', 'community'])
      .map(([x, y]) => [round(x), round(y)])).toMatchSnapshot('cluster-positions');
  });

  it('applyRepulsionAndRecenter enforces the default minimum gap', () => {
    const stars = [
      { _ox: 0, _oy: 0, radius: 10 },
      { _ox: 4, _oy: 0, radius: 10 },
      { _ox: -3, _oy: 2, radius: 5 },
    ];
    applyRepulsionAndRecenter(stars);
    expect(stars.map((s) => ({ _ox: round(s._ox), _oy: round(s._oy) })))
      .toMatchSnapshot('repulsion-default-gap');
  });

  it('computeMaxExtent adds the recorded star and constellation margins', () => {
    const stars = [{ _clusterCx: 100, _clusterCy: -40, _ox: 10, _oy: 5, radius: 12 }];
    expect(round(computeMaxExtent(stars, []))).toMatchSnapshot('max-extent-stars-only');
    expect(round(computeMaxExtent(stars, [{ cx: 20, cy: 200, spread: 60 }])))
      .toMatchSnapshot('max-extent-with-constellations');
  });
});
