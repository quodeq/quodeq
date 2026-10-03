import test from 'node:test';
import assert from 'node:assert/strict';
import { riskPoint } from './riskScore.js';

test('riskPoint with no violations, no compliance and no severity is the origin', () => {
  assert.deepEqual(riskPoint({}), { x: 0, y: 0, b: 0 });
});

test('riskPoint with violations and criticals, no compliance: undampened', () => {
  const p = riskPoint({ violations: 5, compliance: 0, severity: { critical: 2, major: 1, minor: 3 } });
  assert.equal(p.x, 5);
  assert.equal(p.y, 2 * 100 + 1 * 10 + 3 * 1);
  assert.equal(p.b, 5);
});

test('riskPoint with compliance dampens x and y proportionally to the compliance ratio', () => {
  const p = riskPoint({ violations: 10, compliance: 10, severity: { critical: 1 } });
  const dampen = 1 - (10 / 20) * 0.45;
  assert.equal(p.x, 10 * dampen);
  assert.equal(p.y, 100 * dampen);
  assert.equal(p.b, 20);
});

test('riskPoint with only compliance (no violations, no severity)', () => {
  const p = riskPoint({ violations: 0, compliance: 8 });
  assert.equal(p.x, 0);
  assert.equal(p.y, 0);
  assert.equal(p.b, 8);
});
