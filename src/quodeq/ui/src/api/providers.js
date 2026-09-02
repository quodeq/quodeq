/**
 * AI provider / client config API — the CLI clients an evaluation can run
 * with, provider connection tests, and known/saved provider configurations.
 */

import { request } from './request.js';

/** @returns {Promise<Object[]>} */
export function getAiClients() {
  return request('/ai-clients');
}

/**
 * @param {string} clientId
 * @returns {Promise<Object[]>}
 */
export function getClientModels(clientId) {
  return request(`/ai-clients/${encodeURIComponent(clientId)}/models`);
}

/**
 * Eager validation for the Settings command override field. Same rules
 * the server applies to aiCmdPath when an evaluation starts.
 *
 * @param {string} clientId
 * @param {string} path
 * @returns {Promise<{ok: boolean, error: string | null}>}
 */
export function checkCmdPath(clientId, path) {
  return request(
    `/ai-clients/${encodeURIComponent(clientId)}/cmd-path-check?path=${encodeURIComponent(path)}`,
  );
}

/** @returns {Promise<Object>} Connection test result for the provider */
export function testProviderConnection({ provider, apiBase, model, apiKey }) {
  return request('/provider/test', {
    method: 'POST',
    body: JSON.stringify({ provider, api_base: apiBase, model, api_key: apiKey }),
  });
}

/** @returns {Promise<Object[]>} Known model definitions */
export function getKnownModels() {
  return request('/known-models');
}

/** @returns {Promise<Object[]>} Saved provider configurations */
export function getProviderConfigs() {
  return request('/provider-configs');
}
