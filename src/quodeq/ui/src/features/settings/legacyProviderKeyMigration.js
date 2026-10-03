import { providerKey, PROVIDER_CONFIGURED_MARKER, PROVIDER_SETTING_KEY } from '../../constants.js';

// providerKey() split around a placeholder id: every stored api-key entry is
// `${KEY_PREFIX}<providerId>${KEY_SUFFIX}`.
const ID_PLACEHOLDER = '\u0000';
const [KEY_PREFIX, KEY_SUFFIX] = providerKey(ID_PLACEHOLDER, PROVIDER_SETTING_KEY.API_KEY).split(ID_PLACEHOLDER);

let inFlight = null;

/** Provider ids whose api-key entry in `storage` holds a raw credential. */
function providersWithRawKey(storage) {
  const ids = [];
  for (let i = 0; i < storage.length; i += 1) {
    const name = storage.key(i);
    if (!name || !name.startsWith(KEY_PREFIX) || !name.endsWith(KEY_SUFFIX)) continue;
    const id = name.slice(KEY_PREFIX.length, name.length - KEY_SUFFIX.length);
    const value = storage.getItem(name);
    if (id && value && value !== PROVIDER_CONFIGURED_MARKER) ids.push(id);
  }
  return ids;
}

async function moveKeysToServer(storage, saveProviderKey) {
  let providers;
  try {
    providers = providersWithRawKey(storage);
  } catch (err) {
    console.warn('[legacyProviderKeyMigration] could not read stored provider keys:', err);
    return;
  }
  const failed = [];
  for (const provider of providers) {
    const name = providerKey(provider, PROVIDER_SETTING_KEY.API_KEY);
    try {
      const { stored } = await saveProviderKey(provider, storage.getItem(name));
      if (!stored) throw new Error('Provider key was not stored');
      storage.setItem(name, PROVIDER_CONFIGURED_MARKER);
    } catch (err) {
      failed.push(`${provider} (${err?.message ?? err})`);
    }
  }
  if (failed.length > 0) {
    console.warn(`[legacyProviderKeyMigration] provider keys left in browser storage, retried next launch: ${failed.join(', ')}`);
  }
}

/**
 * Moves raw provider API keys still held in browser storage into the
 * server's secure store and leaves PROVIDER_CONFIGURED_MARKER in their place.
 * A key the server did not store stays where it is and is retried on the
 * next call. Providers are handled one at a time; a call made while a run is
 * in progress shares that run. Never rejects.
 *
 * @param {Storage} storage - browser storage holding the provider settings
 * @param {(provider: string, apiKey: string) => Promise<{stored?: boolean}>} saveProviderKey
 * @returns {Promise<void>}
 */
export function migrateLegacyProviderKeys(storage, saveProviderKey) {
  if (!inFlight) {
    inFlight = moveKeysToServer(storage, saveProviderKey).finally(() => {
      inFlight = null;
    });
  }
  return inFlight;
}
