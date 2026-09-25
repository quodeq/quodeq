import { test } from 'node:test';
import assert from 'node:assert/strict';
import { formatScoreDisplay } from './gradeFormatting.js';

test('formatScoreDisplay renders the placeholder dash for NaN', () => {
  assert.equal(formatScoreDisplay(NaN), '—');
  assert.equal(formatScoreDisplay(undefined), '—');
  assert.equal(formatScoreDisplay('not-a-number'), '—');
});

test('formatScoreDisplay renders one decimal place for a number', () => {
  assert.equal(formatScoreDisplay(8.25), '8.3');
  assert.equal(formatScoreDisplay(8), '8.0');
});

test('formatScoreDisplay also accepts a numeric string', () => {
  assert.equal(formatScoreDisplay('8.25'), '8.3');
});
