import test from 'node:test';
import assert from 'node:assert/strict';
import { migrateLegacyProviderKeys } from './legacyProviderKeyMigration.js';
import { PROVIDER_CONFIGURED_MARKER, providerKey, PROVIDER_SETTING_KEY } from '../../constants.js';

const keyOf = (provider) => providerKey(provider, PROVIDER_SETTING_KEY.API_KEY);

function fakeStorage(entries = {}) {
  const store = { ...entries };
  return {
    get length() { return Object.keys(store).length; },
    key: (i) => Object.keys(store)[i] ?? null,
    getItem: (key) => (key in store ? store[key] : null),
    setItem: (key, value) => { store[key] = String(value); },
    removeItem: (key) => { delete store[key]; },
    _store: store,
  };
}

function recordingSave(response = { stored: true }) {
  const calls = [];
  const save = async (provider, apiKey) => {
    calls.push({ provider, apiKey });
    return typeof response === 'function' ? response(provider) : response;
  };
  return { calls, save };
}

async function withQuietWarn(fn) {
  const original = console.warn;
  const warnings = [];
  console.warn = (...args) => { warnings.push(args); };
  try {
    await fn();
  } finally {
    console.warn = original;
  }
  return warnings;
}

test('a raw key is posted to the server store and replaced by the marker', async () => {
  const s = fakeStorage({ [keyOf('claude')]: 'sk-legacy', 'cc-claude-model': 'opus' });
  const { calls, save } = recordingSave();
  await migrateLegacyProviderKeys(s, save);
  assert.deepEqual(calls, [{ provider: 'claude', apiKey: 'sk-legacy' }]);
  assert.equal(s._store[keyOf('claude')], PROVIDER_CONFIGURED_MARKER);
  assert.equal(s._store['cc-claude-model'], 'opus');
});

test('the marker and an empty value are not posted', async () => {
  const s = fakeStorage({ [keyOf('claude')]: PROVIDER_CONFIGURED_MARKER, [keyOf('codex')]: '' });
  const { calls, save } = recordingSave();
  await migrateLegacyProviderKeys(s, save);
  assert.deepEqual(calls, []);
  assert.equal(s._store[keyOf('claude')], PROVIDER_CONFIGURED_MARKER);
  assert.equal(s._store[keyOf('codex')], '');
});

test('a key the server did not store stays in place', async () => {
  const s = fakeStorage({ [keyOf('claude')]: 'sk-legacy' });
  const { calls, save } = recordingSave({ stored: false });
  const warnings = await withQuietWarn(() => migrateLegacyProviderKeys(s, save));
  assert.equal(calls.length, 1);
  assert.equal(s._store[keyOf('claude')], 'sk-legacy');
  assert.equal(warnings.length, 1);
});

test('a rejected post leaves the key in place, warns once and does not throw', async () => {
  const s = fakeStorage({ [keyOf('claude')]: 'sk-a', [keyOf('codex')]: 'sk-b' });
  const save = async () => { throw new Error('offline'); };
  const warnings = await withQuietWarn(() => migrateLegacyProviderKeys(s, save));
  assert.equal(s._store[keyOf('claude')], 'sk-a');
  assert.equal(s._store[keyOf('codex')], 'sk-b');
  assert.equal(warnings.length, 1);
  assert.ok(!String(warnings[0]).includes('sk-a'));
});

test('two providers are handled one after the other', async () => {
  const s = fakeStorage({ [keyOf('claude')]: 'sk-a', [keyOf('codex')]: 'sk-b' });
  let active = 0;
  let maxActive = 0;
  const calls = [];
  const save = async (provider, apiKey) => {
    active += 1;
    maxActive = Math.max(maxActive, active);
    calls.push({ provider, apiKey });
    await new Promise((resolve) => setTimeout(resolve, 1));
    active -= 1;
    return { stored: true };
  };
  await migrateLegacyProviderKeys(s, save);
  assert.equal(maxActive, 1);
  assert.deepEqual(calls, [
    { provider: 'claude', apiKey: 'sk-a' },
    { provider: 'codex', apiKey: 'sk-b' },
  ]);
  assert.equal(s._store[keyOf('claude')], PROVIDER_CONFIGURED_MARKER);
  assert.equal(s._store[keyOf('codex')], PROVIDER_CONFIGURED_MARKER);
});

test('a second call during a run shares it instead of posting again', async () => {
  const s = fakeStorage({ [keyOf('claude')]: 'sk-legacy' });
  const { calls, save } = recordingSave();
  const first = migrateLegacyProviderKeys(s, save);
  const second = migrateLegacyProviderKeys(s, save);
  assert.equal(first, second);
  await Promise.all([first, second]);
  assert.equal(calls.length, 1);
});

test('unreadable storage does not throw', async () => {
  const s = {
    get length() { throw new Error('blocked'); },
    key: () => null,
    getItem: () => null,
    setItem: () => {},
  };
  const { calls, save } = recordingSave();
  const warnings = await withQuietWarn(() => migrateLegacyProviderKeys(s, save));
  assert.deepEqual(calls, []);
  assert.equal(warnings.length, 1);
});
