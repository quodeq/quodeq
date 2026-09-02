import { useEffect, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { useOmlxServerStatus } from './useOmlxServerStatus.js';
import { t } from '../../../strings/index.js';

/**
 * OmlxTab.jsx's models query plus its offline->online invalidation effect.
 * Extracted verbatim.
 */
export function useOmlxModels({ apiBase, apiKey }) {
  const { getOmlxModels } = useApi();
  const omlxStatus = useOmlxServerStatus(apiBase || undefined);

  const queryClient = useQueryClient();
  const { data: models = [], error: modelsQueryError } = useQuery({
    queryKey: ['settings', 'omlxModels', apiBase, apiKey],
    queryFn: () => getOmlxModels(apiBase || undefined, apiKey || undefined),
  });
  const modelsError = modelsQueryError
    ? t('settings.omlxModelsLoadFailed')
    : null;

  const prevStatusRef = useRef(omlxStatus?.status ?? 'offline');
  useEffect(() => {
    const status = omlxStatus?.status ?? 'offline';
    if (prevStatusRef.current !== 'online' && status === 'online') {
      queryClient.invalidateQueries({ queryKey: ['settings', 'omlxModels'] });
    }
    prevStatusRef.current = status;
  }, [omlxStatus?.status, queryClient]);

  return { omlxStatus, models, modelsError };
}
