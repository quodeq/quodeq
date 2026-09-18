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

describe('galaxyViewScene — parseFloat NaN guards', () => {
  it('computePrincipleScore falls through to the grade/ratio chain instead of returning NaN for a non-numeric rawScore', () => {
    expect(computePrincipleScore('not-a-number', 'A', 1, 3)).not.toBeNaN();
    // With no grade either, falls through to the compliance ratio.
    expect(computePrincipleScore('not-a-number', null, 1, 3)).toBeCloseTo((3 / 4) * 10);
  });

  it('buildScene does not produce a NaN star score when overallScore is not numeric', () => {
    const dims = [{ dimension: 'clean', overallScore: 'N/A', violations: [], compliance: [], principles: [] }];
    const scene = buildScene(dims, 800, 600, {});
    expect(scene.stars[0].score).not.toBeNaN();
  });

  it('updateSceneLiveData does not produce a NaN star score when the live overallScore is not numeric', () => {
    const dims = [{ dimension: 'clean', overallScore: 5, violations: [], compliance: [], principles: [] }];
    const scene = buildScene(dims, 800, 600, {});
    const dimsUpdated = [{ dimension: 'clean', overallScore: 'garbage', violations: [], compliance: [], principles: [] }];
    updateSceneLiveData(scene, dimsUpdated);
    expect(scene.stars[0].score).not.toBeNaN();
  });
});
