import test from 'node:test';
import assert from 'node:assert/strict';
import { roundOneDecimal } from './rounding.js';

test('roundOneDecimal: keeps one decimal and rounds half up (toward +Infinity), Math.round\'s rule', () => {
  assert.equal(roundOneDecimal(7.25), 7.3);
  assert.equal(roundOneDecimal(7.24), 7.2);
  assert.equal(roundOneDecimal(-7.25), -7.2);
  assert.equal(roundOneDecimal(0), 0);
  assert.equal(roundOneDecimal(10), 10);
});
