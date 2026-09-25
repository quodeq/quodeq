import test from 'node:test';
import assert from 'node:assert/strict';
import { clusterFade, fadeOutFrom, unfocusedClusterAlpha } from './galaxyFade.js';
import { UNFOCUSED_CLUSTER_MIN_ALPHA } from './galaxyTuning.js';

test('fadeOutFrom is 1 at the level and loses 1 per span of zoom past it (unclamped above 1)', () => {
  assert.deepEqual([fadeOutFrom(1, 2, 4), fadeOutFrom(2, 2, 4), fadeOutFrom(3, 2, 4)], [1.25, 1, 0.75]);
});

test('fadeOutFrom bottoms out at zero past the span', () => {
  assert.equal(fadeOutFrom(10, 2, 4), 0);
});

test('unfocusedClusterAlpha fades with zoom but never below the unfocused floor', () => {
  assert.deepEqual([unfocusedClusterAlpha(1), unfocusedClusterAlpha(2), unfocusedClusterAlpha(50)], [1, 0.5, UNFOCUSED_CLUSTER_MIN_ALPHA]);
});

test('clusterFade is 1 at the galaxy zoom and 0 a full cluster span past it', () => {
  assert.deepEqual([clusterFade(1), clusterFade(2), clusterFade(3), clusterFade(9)], [1, 0.5, 0, 0]);
});
