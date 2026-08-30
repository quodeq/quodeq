import test from 'node:test';
import assert from 'node:assert/strict';
import {
  migrateLegacyProviderSettings,
  MIGRATION_DONE_KEY,
  LEGACY_AI_CMD_KEY,
  LEGACY_SETTING_MIGRATIONS,
} from './legacySettingsMigration.js';

// Characterization test written BEFORE moving this logic out of
// ProviderTabs.jsx — it runs once per user, ever, so every quirk below is
// pinned exactly as the original inline implementation behaved.

function fakeStorage(entries = {}) {
  const store = { ...entries };
  return {
    getItem: (key) => (key in store ? store[key] : null),
    setItem: (key, value) => { store[key] = String(value); },
    removeItem: (key) => { delete store[key]; },
    _store: store,
  };
}

test('LEGACY_SETTING_MIGRATIONS is the verbatim key map', () => {
  assert.deepEqual(LEGACY_SETTING_MIGRATIONS, {
    'cc-max-subagents': 'subagents',
    'cc-pool-budget': 'time-limit',
    'cc-time-limit': 'time-limit',
    'cc-per-dimension': 'per-dimension',
    'cc-ai-model': 'model',
  });
});

test('no-op when there are no clients yet (early exit, clients.length === 0)', () => {
  const s = fakeStorage({ 'cc-max-subagents': '4' });
  const result = migrateLegacyProviderSettings([], s);
  assert.deepEqual(result, { migrated: false, movedKeys: [] });
  // Nothing touched: the legacy key survives, MIGRATION_DONE_KEY was never set.
  assert.equal(s._store['cc-max-subagents'], '4');
  assert.equal(MIGRATION_DONE_KEY in s._store, false);
});

test('MIGRATION_DONE_KEY guard is truthiness, not a specific sentinel value', () => {
  const s = fakeStorage({ [MIGRATION_DONE_KEY]: 'anything-truthy', 'cc-max-subagents': '4' });
  const result = migrateLegacyProviderSettings([{ id: 'claude' }], s);
  assert.deepEqual(result, { migrated: false, movedKeys: [] });
  // Migration already marked done: legacy key is left alone.
  assert.equal(s._store['cc-max-subagents'], '4');
});

test('targets clients[0].id when no legacy active-provider key was ever written', () => {
  const s = fakeStorage({ 'cc-max-subagents': '4' });
  migrateLegacyProviderSettings([{ id: 'claude' }, { id: 'ollama' }], s);
  assert.equal(s._store['cc-claude-subagents'], '4');
});

test(`targets readString(${LEGACY_AI_CMD_KEY}) when present, over clients[0].id`, () => {
  const s = fakeStorage({ [LEGACY_AI_CMD_KEY]: 'ollama', 'cc-max-subagents': '4' });
  migrateLegacyProviderSettings([{ id: 'claude' }, { id: 'ollama' }], s);
  assert.equal(s._store['cc-ollama-subagents'], '4');
  assert.equal('cc-claude-subagents' in s._store, false);
});

test("oldVal !== null (NOT truthiness) — '0' and '' must migrate", () => {
  const s = fakeStorage({ 'cc-max-subagents': '0', 'cc-per-dimension': '' });
  migrateLegacyProviderSettings([{ id: 'claude' }], s);
  assert.equal(s._store['cc-claude-subagents'], '0');
  assert.equal(s._store['cc-claude-per-dimension'], '');
});

test('an unset legacy key is left alone (not migrated as an empty write)', () => {
  const s = fakeStorage({});
  const result = migrateLegacyProviderSettings([{ id: 'claude' }], s);
  assert.equal('cc-claude-subagents' in s._store, false);
  assert.deepEqual(result.movedKeys, []);
});

test('writes under the cc-${targetId}-${newSuffix} template and removes the old key', () => {
  const s = fakeStorage({ 'cc-time-limit': '600' });
  migrateLegacyProviderSettings([{ id: 'claude' }], s);
  assert.equal(s._store['cc-claude-time-limit'], '600');
  assert.equal('cc-time-limit' in s._store, false);
});

test('migrates every configured legacy key present and reports movedKeys', () => {
  const s = fakeStorage({
    'cc-max-subagents': '3',
    'cc-pool-budget': '900',
    'cc-per-dimension': 'true',
    'cc-ai-model': 'gpt-5',
  });
  const result = migrateLegacyProviderSettings([{ id: 'claude' }], s);
  assert.equal(s._store['cc-claude-subagents'], '3');
  assert.equal(s._store['cc-claude-time-limit'], '900');
  assert.equal(s._store['cc-claude-per-dimension'], 'true');
  assert.equal(s._store['cc-claude-model'], 'gpt-5');
  assert.equal(result.migrated, true);
  assert.deepEqual(
    result.movedKeys.sort(),
    ['cc-ai-model', 'cc-max-subagents', 'cc-per-dimension', 'cc-pool-budget'].sort(),
  );
});

test('cc-time-limit and cc-pool-budget both land on the same new key (last one wins)', () => {
  const s = fakeStorage({ 'cc-pool-budget': '900', 'cc-time-limit': '1200' });
  migrateLegacyProviderSettings([{ id: 'claude' }], s);
  // Object.entries order is insertion order of LEGACY_SETTING_MIGRATIONS:
  // cc-pool-budget is processed before cc-time-limit, so the latter's write
  // is what survives.
  assert.equal(s._store['cc-claude-time-limit'], '1200');
});

test('sets MIGRATION_DONE_KEY after running, so a second call is a no-op', () => {
  const s = fakeStorage({ 'cc-max-subagents': '4' });
  migrateLegacyProviderSettings([{ id: 'claude' }], s);
  assert.equal(s._store[MIGRATION_DONE_KEY], '1');

  // Simulate a second mount with a leftover legacy key that somehow
  // reappeared: it must NOT be migrated again.
  s._store['cc-max-subagents'] = '99';
  const second = migrateLegacyProviderSettings([{ id: 'claude' }], s);
  assert.deepEqual(second, { migrated: false, movedKeys: [] });
  assert.equal(s._store['cc-max-subagents'], '99');
});
