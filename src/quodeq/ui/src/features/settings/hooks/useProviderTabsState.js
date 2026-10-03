import { useState } from 'react';
import { ACTIVE_PROVIDER_KEY, notifyProviderSettingsChanged } from '../../../constants.js';
import { useMigrateLegacySettings } from './useMigrateLegacySettings.js';
import { useAiClientList } from './useAiClientList.js';
import { readString, writeString } from '../../../adapters/storage.js';

/**
 * The analysis provider picker's state: the AI-client list, the active tab
 * (persisted, defaulting to the first installed client once the list
 * loads) and the tab-selection handler.
 */
export function useProviderTabsState(providerConfigs) {
  const [activeTab, setActiveTab] = useState(() => readString(ACTIVE_PROVIDER_KEY) || '');
  const { clients, clientsError } = useAiClientList(providerConfigs, (list) => {
    if (!activeTab && list.length > 0) {
      const firstInstalled = list.find((c) => c.installed !== false) || list[0];
      setActiveTab(firstInstalled.id);
      writeString(ACTIVE_PROVIDER_KEY, firstInstalled.id);
    }
  });

  useMigrateLegacySettings(clients);

  const selectTab = (id) => {
    setActiveTab(id);
    writeString(ACTIVE_PROVIDER_KEY, id);
    // The assistant's Default mode follows the analysis provider — tell it to
    // re-read so its displayed provider/model updates live.
    notifyProviderSettingsChanged();
  };

  const active = clients.find((c) => c.id === activeTab);

  return { clients, clientsError, activeTab, active, selectTab };
}
