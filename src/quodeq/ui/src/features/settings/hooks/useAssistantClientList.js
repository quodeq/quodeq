import { useState, useEffect } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { t } from '../../../strings/index.js';

const DEFAULT_PROVIDER_ORDER = 50;

/**
 * AssistantProviderTabs.jsx's AI-client list fetch (sorted by
 * providerConfigs order), extracted verbatim.
 */
export function useAssistantClientList(providerConfigs) {
  const { getAiClients } = useApi();
  const [clients, setClients] = useState([]);
  const [clientsError, setClientsError] = useState(null);

  useEffect(() => {
    getAiClients().then((data) => {
      const raw = data.clients || [];
      const list = [...raw].sort((a, b) => {
        const oa = providerConfigs?.[a.id]?.order ?? DEFAULT_PROVIDER_ORDER;
        const ob = providerConfigs?.[b.id]?.order ?? DEFAULT_PROVIDER_ORDER;
        return oa - ob;
      });
      setClients(list);
      setClientsError(null);
    }).catch(() => { setClients([]); setClientsError(t('settings.providersLoadFailed')); });
  }, []);

  return { clients, clientsError };
}
