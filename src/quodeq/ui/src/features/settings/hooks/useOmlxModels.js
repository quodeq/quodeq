import { useApi } from '../../../api/ApiContext.jsx';
import { useOmlxServerStatus } from './useOmlxServerStatus.js';
import { useProviderModels } from './useProviderModels.js';

// Prefix key: invalidates the models query for every apiBase/apiKey pair.
const MODELS_KEY_PREFIX = ['settings', 'omlxModels'];

/**
 * OmlxTab.jsx's models query plus its offline->online invalidation effect.
 * Extracted verbatim.
 */
export function useOmlxModels({ apiBase, apiKey }) {
  const { getOmlxModels } = useApi();
  const omlxStatus = useOmlxServerStatus(apiBase || undefined);

  const { models, modelsError } = useProviderModels({
    queryKey: [...MODELS_KEY_PREFIX, apiBase, apiKey],
    fetchModels: () => getOmlxModels(apiBase || undefined, apiKey || undefined),
    errorKey: 'settings.omlxModelsLoadFailed',
    serverStatus: omlxStatus?.status,
    invalidateKey: MODELS_KEY_PREFIX,
  });

  return { omlxStatus, models, modelsError };
}
