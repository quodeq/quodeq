import { useEffect } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { useLlamacppServerStatus } from './useLlamacppServerStatus.js';
import { settingsKeys } from '../../../api/queryKeys.js';
import { useProviderModels } from './useProviderModels.js';
import { PROVIDER_SETTING_KEY } from '../../../constants.js';

const MODELS_KEY = settingsKeys.llamacppModels();

/**
 * LlamaCppTab.jsx's models query plus its two effects (invalidate on
 * offline->online, mirror the loaded model into provider state). Extracted
 * verbatim.
 */
export function useLlamaCppModels({ state, update }) {
  const { getLlamacppModels } = useApi();
  const llamacppStatus = useLlamacppServerStatus();

  const { models, modelsError } = useProviderModels({
    queryKey: MODELS_KEY,
    fetchModels: () => getLlamacppModels(),
    errorKey: 'settings.llamacppLoadFailed',
    serverStatus: llamacppStatus?.status,
  });

  // The model name comes from llama-server itself. Mirror it into provider
  // state so the analysis runner has a model to send.
  useEffect(() => {
    if (models.length && models[0].name && state.model !== models[0].name) {
      update(PROVIDER_SETTING_KEY.MODEL, models[0].name);
    }
  }, [models, state.model, update]);

  return { llamacppStatus, models, modelsError };
}
