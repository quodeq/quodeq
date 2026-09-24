import { DEFAULT_MAX_SUBAGENTS, DEFAULT_TIME_LIMIT_S, SETTING_KEY_TIME_LIMIT } from '../../../constants.js';
import { PROVIDER } from '../../../vocab/provider.js';
import { AI_CLIENT_TYPE } from '../../../api/providers.js';

// Re-exported for callers already importing provider helpers from here.
export { providerSupportsWebTools, WEB_TOOL_PROVIDERS } from '../../../models/provider.js';

// classifyProvider's result: how a provider is reached. Every Settings tab
// that branches on "which kind of provider is this" (ProviderTabs,
// ModelSection, CliProviderTab, ProviderSettings, useAssistantProvider's
// picker) reads this back.
export const PROVIDER_CLASSIFICATION = Object.freeze({
  CLI: 'cli', LOCAL_API: 'local-api', CLOUD_API: 'cloud-api',
});

// These markers must stay in sync with the backend's _LOCAL_API_MARKERS
// in quodeq/llm_bridge/_providers.py (configurable via QUODEQ_LOCAL_API_MARKERS).
const LOCAL_MARKERS = ['11434', 'localhost', '127.0.0.1', 'ollama'];

export function classifyProvider(id, type, config) {
  // `type` is the ai-clients response's own per-client type field
  // (api/providers.js's AI_CLIENT_TYPE), not a PROVIDER_CLASSIFICATION value.
  if (type === AI_CLIENT_TYPE.CLI || !type) return PROVIDER_CLASSIFICATION.CLI;
  const apiBase = (config?.api_base || '').toLowerCase();
  if (LOCAL_MARKERS.some((m) => apiBase.includes(m))) return PROVIDER_CLASSIFICATION.LOCAL_API;
  return PROVIDER_CLASSIFICATION.CLOUD_API;
}

const CLI_DEFAULTS = { 'subagents': String(DEFAULT_MAX_SUBAGENTS), [SETTING_KEY_TIME_LIMIT]: String(DEFAULT_TIME_LIMIT_S) };
const OLLAMA_DEFAULTS = { [SETTING_KEY_TIME_LIMIT]: '0' };
const LLAMACPP_DEFAULTS = { [SETTING_KEY_TIME_LIMIT]: '0' };
const OMLX_DEFAULTS = { [SETTING_KEY_TIME_LIMIT]: '0' };
// Every cloud provider runs with the CLI-style effective defaults
// (5 subagents / 600s — see resolveProviderSettings); the tab must display
// them for unset keys or Settings claims values the run won't use.
const CLOUD_FALLBACK_DEFAULTS = { 'subagents': String(DEFAULT_MAX_SUBAGENTS), [SETTING_KEY_TIME_LIMIT]: String(DEFAULT_TIME_LIMIT_S) };
const CLOUD_DEFAULTS_BY_ID = {
  openrouter: { 'model': 'baidu/cobuddy:free' },
};

/**
 * Display defaults for a provider tab: what an unset key effectively runs
 * with. Exported so tests can pin display == payload.
 */
export function defaultsForProvider(classification, providerId) {
  // The launch command defaults to the provider id itself; the Advanced
  // field shows it pre-filled so changing it is an edit, not a discovery.
  if (classification === PROVIDER_CLASSIFICATION.CLI) return { ...CLI_DEFAULTS, 'cmd-path': providerId };
  if (classification === PROVIDER_CLASSIFICATION.LOCAL_API) {
    if (providerId === PROVIDER.LLAMACPP) return LLAMACPP_DEFAULTS;
    if (providerId === PROVIDER.OMLX) return OMLX_DEFAULTS;
    return OLLAMA_DEFAULTS;
  }
  return { ...CLOUD_FALLBACK_DEFAULTS, ...(CLOUD_DEFAULTS_BY_ID[providerId] || {}) };
}
