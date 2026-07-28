import { ACTIVE_PROVIDER_KEY, providerKey } from '../../../constants.js';

/**
 * The active provider/model pair the next run would use, for the identity
 * strips' "model" cell. Same storage keys the start payload reads, so the
 * strip can never claim a model the run won't get.
 * @returns {{provider:string, model:string}|null} null when no provider is active
 */
export function readActiveProviderModel(storage = localStorage) {
  const provider = storage.getItem(ACTIVE_PROVIDER_KEY) || '';
  if (!provider) return null;
  const model = storage.getItem(providerKey(provider, 'model')) || '';
  return { provider, model };
}
