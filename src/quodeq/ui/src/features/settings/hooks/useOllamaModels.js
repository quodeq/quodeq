import { useQuery } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { useOllamaServerStatus } from './useOllamaServerStatus.js';
import { settingsKeys } from '../../../api/queryKeys.js';
import { t } from '../../../strings/index.js';
import { useInvalidateOnOnline } from './useInvalidateOnOnline.js';

const MODELS_KEY = settingsKeys.ollamaModels();

/**
 * OllamaTab.jsx's models query plus its offline->online invalidation
 * effect. Extracted verbatim.
 */
export function useOllamaModels() {
  const { getOllamaModels } = useApi();
  const ollamaStatus = useOllamaServerStatus();

  const { data: models = [], error: modelsQueryError } = useQuery({
    queryKey: MODELS_KEY,
    queryFn: () => getOllamaModels(),
  });
  const modelsError = modelsQueryError
    ? t('settings.ollamaModelsLoadFailed')
    : null;

  useInvalidateOnOnline(ollamaStatus?.status, MODELS_KEY);

  return { ollamaStatus, models, modelsError };
}
