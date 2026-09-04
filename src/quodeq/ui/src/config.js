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

// Mirrors shared/defaults.json's dashboard_port (see QUODEQ_DASHBOARD_PORT on
// the Python side, src/quodeq/shared/_env.py::get_dashboard_port). Kept as a
// runtime-overridable value here too so a non-default dashboard port can be
// reflected without a rebuild.
export const DASHBOARD_BASE_PORT = _runtimeConfig.dashboardBasePort || 7863;
