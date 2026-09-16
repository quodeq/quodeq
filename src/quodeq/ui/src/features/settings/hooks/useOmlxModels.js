import { useQuery } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { useOmlxServerStatus } from './useOmlxServerStatus.js';
import { t } from '../../../strings/index.js';
import { useInvalidateOnOnline } from './useInvalidateOnOnline.js';

// Prefix key: invalidates the models query for every apiBase/apiKey pair.
const MODELS_KEY_PREFIX = ['settings', 'omlxModels'];

/**
 * OmlxTab.jsx's models query plus its offline->online invalidation effect.
 * Extracted verbatim.
 */
export function useOmlxModels({ apiBase, apiKey }) {
  const { getOmlxModels } = useApi();
  const omlxStatus = useOmlxServerStatus(apiBase || undefined);

  const { data: models = [], error: modelsQueryError } = useQuery({
    queryKey: ['settings', 'omlxModels', apiBase, apiKey],
    queryFn: () => getOmlxModels(apiBase || undefined, apiKey || undefined),
  });
  const modelsError = modelsQueryError
    ? t('settings.omlxModelsLoadFailed')
    : null;

  useInvalidateOnOnline(omlxStatus?.status, MODELS_KEY_PREFIX);

  return { omlxStatus, models, modelsError };
}
