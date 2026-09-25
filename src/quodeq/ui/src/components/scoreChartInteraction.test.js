import test from 'node:test';
import assert from 'node:assert/strict';
import { runChartInteraction } from './scoreChartHelpers.js';

test('runChartInteraction activates a point by its run id', () => {
  const clicked = [];
  const setHoveredIndex = () => {};
  const interaction = runChartInteraction({
    hoveredIndex: 2, setHoveredIndex, selectedRunId: 'r1', onBarClick: (id) => clicked.push(id),
  });
  assert.equal(interaction.hoveredIndex, 2);
  assert.equal(interaction.setHoveredIndex, setHoveredIndex);
  assert.equal(interaction.selectedRunId, 'r1');
  interaction.onActivate({ runId: 'r9' });
  assert.deepEqual(clicked, ['r9']);
});

test('runChartInteraction leaves points inert without a click handler', () => {
  const interaction = runChartInteraction({ hoveredIndex: null, setHoveredIndex: () => {}, selectedRunId: null });
  assert.equal(interaction.onActivate, undefined);
  assert.deepEqual(Object.keys(interaction), ['hoveredIndex', 'setHoveredIndex', 'selectedRunId', 'onActivate']);
});
