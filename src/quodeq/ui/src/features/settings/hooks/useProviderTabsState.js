import { useState, useEffect } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { ACTIVE_PROVIDER_KEY, notifyProviderSettingsChanged } from '../../../constants.js';
import { useMigrateLegacySettings } from './useMigrateLegacySettings.js';
import { t } from '../../../strings/index.js';
import { sortClientsByProviderOrder } from './providerClientOrder.js';
import { readString, writeString } from '../../../adapters/storage.js';

/**
 * ProviderTabs.jsx's client-list fetch, active-tab state and tab-selection
 * handler. Extracted verbatim.
 */
export function useProviderTabsState(providerConfigs) {
  const { getAiClients } = useApi();
  const [clients, setClients] = useState([]);
  const [clientsError, setClientsError] = useState(null);
  const [activeTab, setActiveTab] = useState(() => readString(ACTIVE_PROVIDER_KEY) || '');

  useMigrateLegacySettings(clients);

  useEffect(() => {
    getAiClients().then((data) => {
      const raw = data.clients || [];
      // Sort by 'order' field from provider configs (ai_providers.json)
      const list = sortClientsByProviderOrder(raw, providerConfigs);
      setClients(list);
      if (!activeTab && list.length > 0) {
        const firstInstalled = list.find((c) => c.installed !== false) || list[0];
        setActiveTab(firstInstalled.id);
        writeString(ACTIVE_PROVIDER_KEY, firstInstalled.id);
      }
      setClientsError(null);
    }).catch(() => { setClients([]); setClientsError(t('settings.providersLoadFailed')); });
  }, []);

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
