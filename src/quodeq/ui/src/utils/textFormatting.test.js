import { test } from 'node:test';
import assert from 'node:assert/strict';
import { complianceRatio } from './textFormatting.js';

test('complianceRatio reads violations : compliance as a whole number', () => {
  assert.equal(complianceRatio(2177, 1922), '1:1');
  assert.equal(complianceRatio(3, 10), '1:3');
  assert.equal(complianceRatio(100, 500), '1:5');
});

test('complianceRatio without violations keeps the placeholder', () => {
  assert.equal(complianceRatio(0, 5), '—');
});
