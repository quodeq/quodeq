/**
 * The models query every local-provider tab runs.
 *
 * Ollama, llama.cpp and MLX all fetch a model list, default it to an empty
 * array, translate any failure into one message, and re-fetch when the server
 * comes back online. Only the key, the fetch and the message key differ.
 */
import { useQuery } from '@tanstack/react-query';
import { t } from '../../../strings/index.js';
import { useInvalidateOnOnline } from './useInvalidateOnOnline.js';

/**
 * Fetch a provider's model list and keep it fresh across reconnects.
 *
 * @param {Object} options
 * @param {Array} options.queryKey React Query key for this provider's models.
 * @param {() => Promise<Array>} options.fetchModels The provider's list call.
 * @param {string} options.errorKey Translation key for the load-failure message.
 * @param {string|undefined} options.serverStatus The provider server's status, watched for offline->online.
 * @param {Array} [options.invalidateKey] Key to invalidate on reconnect; defaults to `queryKey`.
 * @returns {{models: Array, modelsError: string|null}}
 */
export function useProviderModels({ queryKey, fetchModels, errorKey, serverStatus, invalidateKey }) {
  const { data: models = [], error: modelsQueryError } = useQuery({
    queryKey,
    queryFn: fetchModels,
  });
  const modelsError = modelsQueryError ? t(errorKey) : null;

  useInvalidateOnOnline(serverStatus, invalidateKey || queryKey);

  return { models, modelsError };
}
