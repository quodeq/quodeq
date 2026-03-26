/**
 * Shared application configuration.
 *
 * Values can be overridden at runtime by setting window.__QUODEQ_CONFIG__
 * before the app loads (e.g. in index.html or via a config script).
 */

const _runtimeConfig = (typeof window !== 'undefined' && window.__QUODEQ_CONFIG__) || {};

export const SERVER_PROTOCOL = _runtimeConfig.serverProtocol || 'http';
export const SERVER_HOST = _runtimeConfig.serverHost || '127.0.0.1';
export const SERVER_BASE_URL = _runtimeConfig.serverBaseUrl || `${SERVER_PROTOCOL}://${SERVER_HOST}`;
