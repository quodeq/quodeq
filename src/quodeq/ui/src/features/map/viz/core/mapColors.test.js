import test from 'node:test';
import assert from 'node:assert/strict';
import { worstSeverity, nodeColor, nodeBorderColor } from './mapColors.js';

test('worstSeverity: returns the highest severity present', () => {
  assert.equal(worstSeverity({ critical: 1, major: 0, minor: 0 }), 'critical');
  assert.equal(worstSeverity({ critical: 0, major: 1, minor: 0 }), 'major');
  assert.equal(worstSeverity({ critical: 0, major: 0, minor: 1 }), 'minor');
  assert.equal(worstSeverity({ critical: 0, major: 0, minor: 0 }), null);
});

test('worstSeverity: does not throw and returns null when severity is undefined/null', () => {
  assert.doesNotThrow(() => worstSeverity(undefined));
  assert.equal(worstSeverity(undefined), null);
  assert.equal(worstSeverity(null), null);
});

test('nodeColor/nodeBorderColor: do not throw when node.severity is missing', () => {
  const node = { violations: 0, compliance: 0 };
  assert.doesNotThrow(() => nodeColor(node, 'violations'));
  assert.doesNotThrow(() => nodeBorderColor(node, 'violations'));
});
