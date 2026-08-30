import { useEffect } from 'react';
import { migrateLegacyProviderSettings } from '../legacySettingsMigration.js';

/**
 * Runs the one-time legacy-settings migration once the installed client
 * list is known (see legacySettingsMigration.js for exactly what moves).
 */
export function useMigrateLegacySettings(clients) {
  useEffect(() => {
    migrateLegacyProviderSettings(clients);
  }, [clients]);
}
