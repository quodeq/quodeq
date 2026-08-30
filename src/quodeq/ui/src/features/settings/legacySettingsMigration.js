import { readString, removeKey, writeString } from '../../adapters/storage.js';

export const MIGRATION_DONE_KEY = 'cc-provider-tabs-migrated';
export const LEGACY_AI_CMD_KEY = 'cc-ai-cmd';
export const LEGACY_SETTING_MIGRATIONS = {
  'cc-max-subagents': 'subagents',
  // Legacy global key — migrate to provider-scoped 'time-limit' suffix.
  'cc-pool-budget': 'time-limit',
  'cc-time-limit': 'time-limit',
  'cc-per-dimension': 'per-dimension',
  'cc-ai-model': 'model',
};

/**
 * One-time migration of legacy global settings keys (from before Settings
 * had per-provider tabs) into the provider-scoped `cc-<id>-<setting>` shape.
 * Runs once per user, ever — gated by MIGRATION_DONE_KEY.
 *
 * @param {Array<{id: string}>} clients - installed AI clients; migration is
 *   skipped until at least one exists, and targets the previously-active
 *   provider (LEGACY_AI_CMD_KEY) or clients[0] otherwise.
 * @param {*} [storage] - injectable storage backend (adapters/storage.js)
 * @returns {{migrated: boolean, movedKeys: string[]}}
 */
export function migrateLegacyProviderSettings(clients, storage) {
  if (clients.length === 0) return { migrated: false, movedKeys: [] };
  if (readString(MIGRATION_DONE_KEY, null, storage)) return { migrated: false, movedKeys: [] };
  const targetId = readString(LEGACY_AI_CMD_KEY, null, storage) || clients[0].id;
  const movedKeys = [];
  for (const [oldKey, newSuffix] of Object.entries(LEGACY_SETTING_MIGRATIONS)) {
    const oldVal = readString(oldKey, null, storage);
    if (oldVal !== null) {
      writeString(`cc-${targetId}-${newSuffix}`, oldVal, storage);
      removeKey(oldKey, storage);
      movedKeys.push(oldKey);
    }
  }
  writeString(MIGRATION_DONE_KEY, '1', storage);
  return { migrated: true, movedKeys };
}
