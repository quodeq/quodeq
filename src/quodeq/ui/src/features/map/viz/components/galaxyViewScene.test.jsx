/**
 * NaN guards on parseFloat(overallScore/rawScore). scoreRGB() (used by
 * buildDimStar) reads theme colours through a 1x1 canvas, which JSDOM does
 * not implement (vitest.setup.js stubs getContext() to return null); stub a
 * minimal 2D context here so buildScene/updateSceneLiveData can run.
 */
import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { buildScene, computePrincipleScore, updateSceneLiveData } from './galaxyViewScene.js';

let originalGetContext;
beforeAll(() => {
  originalGetContext = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function stubGetContext() {
    return {
      clearRect: () => {},
      fillRect: () => {},
      fillStyle: '',
      getImageData: () => ({ data: [128, 128, 128, 255] }),
    };
  };
});
afterAll(() => {
  HTMLCanvasElement.prototype.getContext = originalGetContext;
});

const DEFAULT_STAR_SCORE = 5; // buildDimStar/updateSceneLiveData's documented fallback

describe('galaxyViewScene — parseFloat NaN guards', () => {
  it('computePrincipleScore falls through to the grade/ratio chain, landing on the documented default, for a non-numeric rawScore', () => {
    // Grade still resolves to a real (non-NaN) numeric score.
    expect(computePrincipleScore('not-a-number', 'A', 1, 3)).not.toBeNaN();
    // With no grade either, falls through to the compliance ratio.
    expect(computePrincipleScore('not-a-number', null, 1, 3)).toBeCloseTo((3 / 4) * 10);
    // With no grade and no violations/compliance either, lands on the
    // documented neutral default rather than NaN.
    expect(computePrincipleScore('not-a-number', null, 0, 0)).toBe(DEFAULT_STAR_SCORE);
  });

  it('computePrincipleScore treats a rawScore of 0 as a real score, not an absent one', () => {
    // `if (rawScore)` would have treated 0 as falsy and fallen through to
    // the grade; Number.isFinite keeps it as the actual 0 score.
    expect(computePrincipleScore(0, 'A', 1, 3)).toBe(0);
    expect(computePrincipleScore('0', 'A', 1, 3)).toBe(0);
  });

  it('buildScene falls back to the documented default star score when overallScore is not numeric', () => {
    const dims = [{ dimension: 'clean', overallScore: 'N/A', violations: [], compliance: [], principles: [] }];
    const scene = buildScene(dims, 800, 600, {});
    expect(scene.stars[0].score).toBe(DEFAULT_STAR_SCORE);
  });

  it('buildScene keeps an overallScore of 0 as 0, not the default', () => {
    const dims = [{ dimension: 'clean', overallScore: 0, violations: [], compliance: [], principles: [] }];
    const scene = buildScene(dims, 800, 600, {});
    expect(scene.stars[0].score).toBe(0);
  });

  it('updateSceneLiveData falls back to the documented default star score when the live overallScore is not numeric', () => {
    const dims = [{ dimension: 'clean', overallScore: 5, violations: [], compliance: [], principles: [] }];
    const scene = buildScene(dims, 800, 600, {});
    const dimsUpdated = [{ dimension: 'clean', overallScore: 'garbage', violations: [], compliance: [], principles: [] }];
    updateSceneLiveData(scene, dimsUpdated);
    expect(scene.stars[0].score).toBe(DEFAULT_STAR_SCORE);
  });

  it('updateSceneLiveData keeps a live overallScore of 0 as 0, not the default', () => {
    const dims = [{ dimension: 'clean', overallScore: 5, violations: [], compliance: [], principles: [] }];
    const scene = buildScene(dims, 800, 600, {});
    const dimsUpdated = [{ dimension: 'clean', overallScore: 0, violations: [], compliance: [], principles: [] }];
    updateSceneLiveData(scene, dimsUpdated);
    expect(scene.stars[0].score).toBe(0);
  });
});
