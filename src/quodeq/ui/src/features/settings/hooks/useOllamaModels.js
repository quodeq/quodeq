import { useApi } from '../../../api/ApiContext.jsx';
import { useOllamaServerStatus } from './useOllamaServerStatus.js';
import { settingsKeys } from '../../../api/queryKeys.js';
import { useProviderModels } from './useProviderModels.js';

const MODELS_KEY = settingsKeys.ollamaModels();

/**
 * OllamaTab.jsx's models query plus its offline->online invalidation
 * effect. Extracted verbatim.
 */
export function useOllamaModels() {
  const { getOllamaModels } = useApi();
  const ollamaStatus = useOllamaServerStatus();

  const { models, modelsError } = useProviderModels({
    queryKey: MODELS_KEY,
    fetchModels: () => getOllamaModels(),
    errorKey: 'settings.ollamaModelsLoadFailed',
    serverStatus: ollamaStatus?.status,
  });

  return { ollamaStatus, models, modelsError };
}
