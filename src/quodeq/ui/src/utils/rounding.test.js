import test from 'node:test';
import assert from 'node:assert/strict';
import { roundOneDecimal, roundOneDecimalLikeServer } from './rounding.js';

test('roundOneDecimal: keeps one decimal and rounds half up (toward +Infinity), Math.round\'s rule', () => {
  assert.equal(roundOneDecimal(7.25), 7.3);
  assert.equal(roundOneDecimal(7.24), 7.2);
  assert.equal(roundOneDecimal(-7.25), -7.2);
  assert.equal(roundOneDecimal(0), 0);
  assert.equal(roundOneDecimal(10), 10);
});

test('roundOneDecimalLikeServer: Python round(n, 1), the server\'s rule', () => {
  // 8.85 is 8.8499... in floating point: the server reads 8.8.
  assert.equal(roundOneDecimalLikeServer(8.85), 8.8);
  assert.equal(roundOneDecimalLikeServer(35.4 / 4), 8.8);
  // Exact ties go to the even tenth.
  assert.equal(roundOneDecimalLikeServer(8.25), 8.2);
  assert.equal(roundOneDecimalLikeServer(8.75), 8.8);
  assert.equal(roundOneDecimalLikeServer(-8.25), -8.2);
  assert.equal(roundOneDecimalLikeServer(7.24), 7.2);
  assert.equal(roundOneDecimalLikeServer(10), 10);
});
