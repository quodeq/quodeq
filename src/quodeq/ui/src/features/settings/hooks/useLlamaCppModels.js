import { useEffect, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { useLlamacppServerStatus } from './useLlamacppServerStatus.js';
import { settingsKeys } from '../../../api/queryKeys.js';
import { t } from '../../../strings/index.js';

/**
 * LlamaCppTab.jsx's models query plus its two effects (invalidate on
 * offline->online, mirror the loaded model into provider state). Extracted
 * verbatim.
 */
export function useLlamaCppModels({ state, update }) {
  const { getLlamacppModels } = useApi();
  const llamacppStatus = useLlamacppServerStatus();

  const queryClient = useQueryClient();
  const { data: models = [], error: modelsQueryError } = useQuery({
    queryKey: settingsKeys.llamacppModels(),
    queryFn: () => getLlamacppModels(),
  });
  const modelsError = modelsQueryError
    ? t('settings.llamacppLoadFailed')
    : null;

  // When llama-server transitions offline -> online, refresh the models query
  // so the loaded model populates as soon as the status pill flips to green.
  const prevStatusRef = useRef(llamacppStatus?.status ?? 'offline');
  useEffect(() => {
    const status = llamacppStatus?.status ?? 'offline';
    if (prevStatusRef.current !== 'online' && status === 'online') {
      queryClient.invalidateQueries({ queryKey: settingsKeys.llamacppModels() });
    }
    prevStatusRef.current = status;
  }, [llamacppStatus?.status, queryClient]);

  // The model name comes from llama-server itself. Mirror it into provider
  // state so the analysis runner has a model to send.
  useEffect(() => {
    if (models.length && models[0].name && state.model !== models[0].name) {
      update('model', models[0].name);
    }
  }, [models, state.model, update]);

  return { llamacppStatus, models, modelsError };
}
