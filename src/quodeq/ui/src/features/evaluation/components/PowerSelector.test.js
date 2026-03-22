import test from 'node:test';
import assert from 'node:assert/strict';
import { DEFAULT_MODELS, getLevels, LEVELS, STORAGE_KEY, MODEL_STORAGE_PREFIX } from './powerLevels.js';

// ---------------------------------------------------------------------------
// getLevels with injectable storage
// ---------------------------------------------------------------------------

test('getLevels with null storage returns defaults', () => {
  const levels = getLevels(null);
  assert.equal(levels.length, 3);
  assert.equal(levels[0].model, DEFAULT_MODELS[1]);
  assert.equal(levels[1].model, DEFAULT_MODELS[2]);
  assert.equal(levels[2].model, DEFAULT_MODELS[3]);
});

test('getLevels with mock storage returns overrides', () => {
  const mockStorage = {
    _data: { [`${MODEL_STORAGE_PREFIX}1`]: 'custom-haiku' },
    getItem(key) { return this._data[key] || null; },
  };
  const levels = getLevels(mockStorage);
  assert.equal(levels[0].model, 'custom-haiku');
  assert.equal(levels[1].model, DEFAULT_MODELS[2]);
});

// ---------------------------------------------------------------------------
// LEVELS mapping (uses runtime defaults, no localStorage dependency)
// ---------------------------------------------------------------------------

test('LEVELS has exactly 3 entries', () => {
  assert.equal(LEVELS.length, 3);
});

test('LEVELS are ordered 1, 2, 3', () => {
  assert.deepEqual(LEVELS.map(l => l.level), [1, 2, 3]);
});

test('level 1 maps to haiku default', () => {
  const l = getLevels(null).find(l => l.level === 1);
  assert.equal(l.model, 'haiku');
  assert.equal(l.label, 'Fast');
});

test('level 2 maps to sonnet default', () => {
  const l = getLevels(null).find(l => l.level === 2);
  assert.equal(l.model, 'sonnet');
  assert.equal(l.label, 'Balanced');
});

test('level 3 maps to opus default', () => {
  const l = getLevels(null).find(l => l.level === 3);
  assert.equal(l.model, 'opus');
  assert.equal(l.label, 'Thorough');
});

test('every level has a non-empty model string', () => {
  for (const { level, model } of LEVELS) {
    assert.equal(typeof model, 'string', `level ${level} model should be a string`);
    assert.ok(model.length > 0, `level ${level} model should be non-empty`);
  }
});

test('every level has a non-empty label string', () => {
  for (const { level, label } of LEVELS) {
    assert.equal(typeof label, 'string', `level ${level} label should be a string`);
    assert.ok(label.length > 0, `level ${level} label should be non-empty`);
  }
});

test('all model IDs are unique', () => {
  const models = LEVELS.map(l => l.model);
  assert.equal(new Set(models).size, models.length);
});

test('all labels are unique', () => {
  const labels = LEVELS.map(l => l.label);
  assert.equal(new Set(labels).size, labels.length);
});

// ---------------------------------------------------------------------------
// STORAGE_KEY
// ---------------------------------------------------------------------------

test('STORAGE_KEY is a non-empty string', () => {
  assert.equal(typeof STORAGE_KEY, 'string');
  assert.ok(STORAGE_KEY.length > 0);
});

test('STORAGE_KEY contains "power" for discoverability', () => {
  assert.ok(STORAGE_KEY.includes('power'));
});

// ---------------------------------------------------------------------------
// Level lookup behaviour (simulates component logic)
// ---------------------------------------------------------------------------

test('looking up a valid level returns the correct entry', () => {
  for (const expected of LEVELS) {
    const found = LEVELS.find(l => l.level === expected.level);
    assert.deepEqual(found, expected);
  }
});

test('looking up an invalid level returns undefined', () => {
  assert.equal(LEVELS.find(l => l.level === 0), undefined);
  assert.equal(LEVELS.find(l => l.level === 4), undefined);
  assert.equal(LEVELS.find(l => l.level === -1), undefined);
});

// ---------------------------------------------------------------------------
// Bar-fill logic (level <= active means filled)
// ---------------------------------------------------------------------------

test('at level 1, only bar 1 is filled', () => {
  const active = 1;
  const filled = LEVELS.filter(l => l.level <= active);
  assert.equal(filled.length, 1);
  assert.equal(filled[0].level, 1);
});

test('at level 2, bars 1 and 2 are filled', () => {
  const active = 2;
  const filled = LEVELS.filter(l => l.level <= active);
  assert.equal(filled.length, 2);
  assert.deepEqual(filled.map(l => l.level), [1, 2]);
});

test('at level 3, all bars are filled', () => {
  const active = 3;
  const filled = LEVELS.filter(l => l.level <= active);
  assert.equal(filled.length, 3);
  assert.deepEqual(filled.map(l => l.level), [1, 2, 3]);
});

// ---------------------------------------------------------------------------
// Default selection (should be 2 = sonnet)
// ---------------------------------------------------------------------------

test('default power level 2 resolves to sonnet', () => {
  const defaultLevel = 2;
  const entry = getLevels(null).find(l => l.level === defaultLevel);
  assert.ok(entry);
  assert.equal(entry.model, DEFAULT_MODELS[2]);
});
