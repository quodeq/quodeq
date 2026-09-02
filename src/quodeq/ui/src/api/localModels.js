/**
 * Local model runtimes API — Ollama, llama.cpp, and omlx connection status,
 * available models, and concurrency tests.
 */

import { request } from './request.js';

// ── Ollama ─────────────────────────────────────────────────────────────

/** @returns {Promise<Object>} Ollama connection status */
export function getOllamaStatus() {
  return request('/ollama/status');
}

/** @returns {Promise<Object[]>} Available Ollama models */
export async function getOllamaModels() {
  const data = await request('/ollama/models');
  return data?.models ?? [];
}

/** @returns {Promise<Object>} Concurrency test results for the given model */
export function testOllamaConcurrency(model) {
  return request('/ollama/test-concurrency', {
    method: 'POST',
    body: JSON.stringify({ model }),
  });
}

// ── llama.cpp ──────────────────────────────────────────────────────────

/** @returns {Promise<Object>} llama.cpp connection status */
export function getLlamacppStatus() {
  return request('/llamacpp/status');
}

/** @returns {Promise<Object>} Whether a llama.cpp log file is configured on the server */
export function getLlamacppLogAvailable() {
  return request('/llamacpp/logs/available');
}

/** @returns {Promise<Object[]>} Loaded llama.cpp model (0 or 1 entries) */
export async function getLlamacppModels() {
  const data = await request('/llamacpp/models');
  return data?.models ?? [];
}

/** @returns {Promise<Object>} Concurrency test results for the loaded model */
export function testLlamacppConcurrency(model) {
  return request('/llamacpp/test-concurrency', {
    method: 'POST',
    body: JSON.stringify({ model: model || '' }),
  });
}

// ── omlx ───────────────────────────────────────────────────────────────

/** @returns {Promise<Object>} omlx connection status */
export function getOmlxStatus(baseUrl) {
  const params = baseUrl ? `?base_url=${encodeURIComponent(baseUrl)}` : '';
  return request(`/omlx/status${params}`);
}

/** @returns {Promise<Object[]>} Available omlx models */
export async function getOmlxModels(baseUrl, apiKey) {
  const params = new URLSearchParams();
  if (baseUrl) params.set('base_url', baseUrl);
  const qs = params.toString() ? `?${params}` : '';
  // The API key travels in a header, never the query string: query strings
  // end up in server access logs and browser history.
  const options = apiKey ? { headers: { 'X-Api-Key': apiKey } } : {};
  const data = await request(`/omlx/models${qs}`, options);
  return data?.models ?? [];
}

/** @returns {Promise<Object>} Concurrency test results for the given model */
export function testOmlxConcurrency(model, baseUrl, apiKey) {
  return request('/omlx/test-concurrency', {
    method: 'POST',
    body: JSON.stringify({ model, base_url: baseUrl || undefined, api_key: apiKey || undefined }),
  });
}
