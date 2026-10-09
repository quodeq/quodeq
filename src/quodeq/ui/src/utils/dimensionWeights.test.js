import test from 'node:test';
import assert from 'node:assert/strict';
import { setDimensionWeights, resetDimensionWeights, weightedMeanScore } from './dimensionWeights.js';

// quodeq-web on 2026-10-09: the server said 8.8, the Overview printed 8.9.
const WEB = [['maintainability', 9.5], ['reliability', 7.8], ['security', 10.0], ['usability', 8.1]];

test('weightedMeanScore: a plain mean rounded like the server, 8.85 reads 8.8', () => {
  resetDimensionWeights();
  assert.equal(weightedMeanScore(WEB), 8.8);
  assert.equal(weightedMeanScore([['security', null], ['usability', 8.1]]), 8.1);
  assert.equal(weightedMeanScore([['security', null]]), null);
});

test('weightedMeanScore: applies the formula weights only while they are switched on', () => {
  const dimensionWeights = { security: 3, reliability: 1 };
  setDimensionWeights({ dimensionWeightsEnabled: true, dimensionWeights });
  assert.equal(weightedMeanScore([['security', 10], ['reliability', 6]]), 9);
  // A dimension the table does not name weighs 1, like the server's default.
  assert.equal(weightedMeanScore([['security', 10], ['usability', 6]]), 9);
  setDimensionWeights({ dimensionWeightsEnabled: false, dimensionWeights });
  assert.equal(weightedMeanScore([['security', 10], ['reliability', 6]]), 8);
  resetDimensionWeights();
});
