import { test } from 'node:test';
import assert from 'node:assert/strict';
import { scoreBarColorVar } from './scoreBarColor.js';

test('boundary scores map to tiers', () => {
  assert.equal(scoreBarColorVar('9'), '--color-grade-top-text');
  assert.equal(scoreBarColorVar('8.9'), '--color-grade-high-text');
  assert.equal(scoreBarColorVar('7'), '--color-grade-high-text');
  assert.equal(scoreBarColorVar('5'), '--color-grade-mid-text');
  assert.equal(scoreBarColorVar('3'), '--color-grade-low-text');
  assert.equal(scoreBarColorVar('2.9'), '--color-grade-bottom-text');
  assert.equal(scoreBarColorVar('8.5/10'), '--color-grade-high-text');
  assert.equal(scoreBarColorVar('n/a'), '--color-accent');
});
