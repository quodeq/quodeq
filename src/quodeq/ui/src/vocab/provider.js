// Mirror of src/quodeq/core/types/provider.py:Provider, plus OMLX: omlx is a
// provider-config id with no Provider member (llm_bridge/_providers.py).
export const PROVIDER = Object.freeze({
  CLAUDE: 'claude', CODEX: 'codex', GEMINI: 'gemini', COPILOT: 'copilot', OLLAMA: 'ollama',
  LLAMACPP: 'llamacpp', OPENROUTER: 'openrouter', CUSTOM: 'custom', OMLX: 'omlx',
});

// Mirror of LOCAL_PROVIDERS in llm_bridge/_providers.py: the fixed-endpoint
// local model servers. They default to no time limit (Settings renders them
// as "Unlimited" and only writes the key once the user edits it), so every
// reader of the stored limit must agree on this list.
export const LOCAL_API_PROVIDERS = new Set([PROVIDER.OLLAMA, PROVIDER.LLAMACPP, PROVIDER.OMLX]);

// Providers where the web toggle does something: claude flips its native
// WebSearch/WebFetch, the local providers get in-process search_web/fetch_url.
// The backend gate is LOCAL_PROVIDERS plus the claude argv path in
// assistant/adapters/_cli_command.py.
export const WEB_TOOL_PROVIDERS = new Set([PROVIDER.CLAUDE, ...LOCAL_API_PROVIDERS]);
