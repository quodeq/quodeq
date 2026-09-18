import { ACTIVE_PROVIDER_KEY, providerKey } from '../../../constants.js';
import { readString } from '../../../adapters/storage.js';

/**
 * The active provider/model pair the next run would use, for the identity
 * strips' "model" cell. Same storage keys the start payload reads, so the
 * strip can never claim a model the run won't get.
 * @returns {{provider:string, model:string}|null} null when no provider is active
 */
export function readActiveProviderModel(storage = localStorage) {
  const provider = readString(ACTIVE_PROVIDER_KEY, '', storage);
  if (!provider) return null;
  const model = readString(providerKey(provider, 'model'), '', storage);
  return { provider, model };
}
