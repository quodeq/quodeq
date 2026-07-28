import test from 'node:test';
import assert from 'node:assert/strict';
import { detectedLanguages, formatBudgetLabel, BUDGET_CHOICES_S } from './scanSummary.js';

test('detectedLanguages: aggregates extensions per language, sorted desc', () => {
  const langs = detectedLanguages({ swift: 5102, m: 51, c: 70, h: 8, sh: 20, bash: 5, json: 400 });
  assert.deepEqual(langs, [
    { name: 'swift', count: 5102 },
    { name: 'c', count: 78 },
    { name: 'objective-c', count: 51 },
    { name: 'bash', count: 25 },
  ]);
});

test('detectedLanguages: drops non-code extensions and respects the limit', () => {
  assert.deepEqual(detectedLanguages({ md: 12, json: 3 }), []);
  const many = detectedLanguages({ py: 5, js: 4, go: 3, rs: 2, rb: 1 }, 2);
  assert.equal(many.length, 2);
  assert.equal(many[0].name, 'python');
});

test('detectedLanguages: tolerates null input', () => {
  assert.deepEqual(detectedLanguages(null), []);
});

test('formatBudgetLabel: m:ss for positive seconds, "no limit" otherwise', () => {
  assert.equal(formatBudgetLabel(300), '5:00');
  assert.equal(formatBudgetLabel(600), '10:00');
  assert.equal(formatBudgetLabel(1800), '30:00');
  assert.equal(formatBudgetLabel(90), '1:30');
  assert.equal(formatBudgetLabel(0), 'no limit');
  assert.equal(formatBudgetLabel(-5), 'no limit');
});

test('BUDGET_CHOICES_S: presets end with the no-limit option', () => {
  assert.equal(BUDGET_CHOICES_S[BUDGET_CHOICES_S.length - 1], 0);
});
