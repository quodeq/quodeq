import { useQuery } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { settingsKeys } from '../../../api/queryKeys.js';
import { t } from '../../../strings/index.js';

const MODELS_STALE_MS = 60_000;

/** Shared account-model discovery for Copilot settings and connection feedback. */
export function useCopilotModels() {
  const api = useApi();
  return useQuery({
    queryKey: settingsKeys.clientModels('copilot'),
    queryFn: async () => {
      const result = await api.getClientModels('copilot');
      if (result?.error) throw new Error(result.error);
      const models = result?.models;
      if (!Array.isArray(models) || !models.length
          || models.some((model) => typeof model !== 'string' || !model.trim())) {
        throw new Error(t('settings.copilotModelsInvalid'));
      }
      return models;
    },
    staleTime: MODELS_STALE_MS,
    retry: false,
  });
}
