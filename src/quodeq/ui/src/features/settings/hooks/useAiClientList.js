import { useState, useEffect } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { t } from '../../../strings/index.js';
import { sortClientsByProviderOrder } from './providerClientOrder.js';

/**
 * The AI-client list both provider pickers show, fetched once on mount and
 * sorted by the providers' configured order.
 * @param {Object} providerConfigs ai_providers.json contents, keyed by provider id.
 * @param {(clients: Array) => void} [onLoaded] Called with the sorted list
 *   after a successful fetch, before the load error is cleared.
 * @returns {{clients: Array, clientsError: string|null}}
 */
export function useAiClientList(providerConfigs, onLoaded) {
  const { getAiClients } = useApi();
  const [clients, setClients] = useState([]);
  const [clientsError, setClientsError] = useState(null);

  useEffect(() => {
    getAiClients().then((data) => {
      const raw = data.clients || [];
      const list = sortClientsByProviderOrder(raw, providerConfigs);
      setClients(list);
      onLoaded?.(list);
      setClientsError(null);
    }).catch(() => { setClients([]); setClientsError(t('settings.providersLoadFailed')); });
  }, []);

  return { clients, clientsError };
}
