import test from 'node:test';
import assert from 'node:assert/strict';
import {
  resolveProviderSettings, effectiveProviderDefaults,
  readActiveProviderSelection, readActiveProviderModel,
} from './effectiveProviderSettings.js';

const storage = (entries) => ({ getItem: (key) => (key in entries ? entries[key] : null) });

test('defaults: local-API providers get 1 subagent / unlimited, others 5 / 600', () => {
  for (const p of ['ollama', 'llamacpp', 'omlx']) {
    assert.deepEqual(
      effectiveProviderDefaults(p),
      { subagents: 1, timeLimitS: 0, perDimension: false, verify: true },
    );
  }
  for (const p of ['claude', 'codex', 'gemini', 'openrouter', 'some-new-cloud']) {
    assert.deepEqual(
      effectiveProviderDefaults(p),
      { subagents: 5, timeLimitS: 600, perDimension: false, verify: true },
    );
  }
});

test('stored values win, including explicit unlimited (0)', () => {
  const s = storage({
    'cc-claude-subagents': '3',
    'cc-claude-time-limit': '0',
    'cc-claude-per-dimension': 'true',
    'cc-claude-verify': 'false',
  });
  assert.deepEqual(
    resolveProviderSettings('claude', s),
    { subagents: 3, timeLimitS: 0, perDimension: true, verify: false },
  );
});

test('unset keys resolve to the effective defaults', () => {
  assert.deepEqual(
    resolveProviderSettings('claude', storage({})),
    { subagents: 5, timeLimitS: 600, perDimension: false, verify: true },
  );
  assert.deepEqual(
    resolveProviderSettings('ollama', storage({})),
    { subagents: 1, timeLimitS: 0, perDimension: false, verify: true },
  );
});

test('corrupt numeric values fall back to defaults instead of NaN', () => {
  const s = storage({ 'cc-claude-subagents': 'abc', 'cc-claude-time-limit': '' });
  assert.deepEqual(
    resolveProviderSettings('claude', s),
    { subagents: 5, timeLimitS: 600, perDimension: false, verify: true },
  );
});

test('legacy pool-budget key is honored when time-limit is unset', () => {
  const s = storage({ 'cc-claude-pool-budget': '1200' });
  assert.equal(resolveProviderSettings('claude', s).timeLimitS, 1200);
});

test('readActiveProviderSelection returns null when unset', () => {
  assert.equal(readActiveProviderSelection(storage({})), null);
});

test('readActiveProviderSelection returns the stored provider id', () => {
  const s = storage({ 'cc-active-provider': 'claude' });
  assert.equal(readActiveProviderSelection(s), 'claude');
});

test('readActiveProviderSelection collapses an explicit empty string to null', () => {
  const s = storage({ 'cc-active-provider': '' });
  assert.equal(readActiveProviderSelection(s), null);
});

test('readActiveProviderModel returns null with no provider id', () => {
  assert.equal(readActiveProviderModel(null, storage({})), null);
  assert.equal(readActiveProviderModel('', storage({})), null);
});

test('readActiveProviderModel returns the stored model for the provider', () => {
  const s = storage({ 'cc-claude-model': 'sonnet' });
  assert.equal(readActiveProviderModel('claude', s), 'sonnet');
});

test('readActiveProviderModel returns null when unset', () => {
  assert.equal(readActiveProviderModel('claude', storage({})), null);
});
