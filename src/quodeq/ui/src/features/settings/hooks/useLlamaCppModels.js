import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { useLlamacppServerStatus } from './useLlamacppServerStatus.js';
import { settingsKeys } from '../../../api/queryKeys.js';
import { t } from '../../../strings/index.js';
import { useInvalidateOnOnline } from './useInvalidateOnOnline.js';

const MODELS_KEY = settingsKeys.llamacppModels();

/**
 * LlamaCppTab.jsx's models query plus its two effects (invalidate on
 * offline->online, mirror the loaded model into provider state). Extracted
 * verbatim.
 */
export function useLlamaCppModels({ state, update }) {
  const { getLlamacppModels } = useApi();
  const llamacppStatus = useLlamacppServerStatus();

  const { data: models = [], error: modelsQueryError } = useQuery({
    queryKey: MODELS_KEY,
    queryFn: () => getLlamacppModels(),
  });
  const modelsError = modelsQueryError
    ? t('settings.llamacppLoadFailed')
    : null;

  useInvalidateOnOnline(llamacppStatus?.status, MODELS_KEY);

  // The model name comes from llama-server itself. Mirror it into provider
  // state so the analysis runner has a model to send.
  useEffect(() => {
    if (models.length && models[0].name && state.model !== models[0].name) {
      update('model', models[0].name);
    }
  }, [models, state.model, update]);

  return { llamacppStatus, models, modelsError };
}
