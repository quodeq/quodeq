import { useEffect, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { useOllamaServerStatus } from './useOllamaServerStatus.js';
import { settingsKeys } from '../../../api/queryKeys.js';
import { t } from '../../../strings/index.js';

/**
 * OllamaTab.jsx's models query plus its offline->online invalidation
 * effect. Extracted verbatim.
 */
export function useOllamaModels() {
  const { getOllamaModels } = useApi();
  const ollamaStatus = useOllamaServerStatus();

  const queryClient = useQueryClient();
  const { data: models = [], error: modelsQueryError } = useQuery({
    queryKey: settingsKeys.ollamaModels(),
    queryFn: () => getOllamaModels(),
  });
  const modelsError = modelsQueryError
    ? t('settings.ollamaModelsLoadFailed')
    : null;

  // When Ollama transitions offline → online, the cached models query is
  // either an empty list or a previous error — neither auto-refetches just
  // because the daemon came up. Invalidate it so the dropdown populates as
  // soon as the status pill flips to green, without requiring a navigation.
  const prevStatusRef = useRef(ollamaStatus?.status ?? 'offline');
  useEffect(() => {
    const status = ollamaStatus?.status ?? 'offline';
    if (prevStatusRef.current !== 'online' && status === 'online') {
      queryClient.invalidateQueries({ queryKey: settingsKeys.ollamaModels() });
    }
    prevStatusRef.current = status;
  }, [ollamaStatus?.status, queryClient]);

  return { ollamaStatus, models, modelsError };
}
