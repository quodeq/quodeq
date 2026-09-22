import { useState, useEffect } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { t } from '../../../strings/index.js';
import { sortClientsByProviderOrder } from './providerClientOrder.js';

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
      const list = sortClientsByProviderOrder(raw, providerConfigs);
      setClients(list);
      setClientsError(null);
    }).catch(() => { setClients([]); setClientsError(t('settings.providersLoadFailed')); });
  }, []);

  return { clients, clientsError };
}
