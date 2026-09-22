/**
 * Providers where the web toggle does something: claude flips its native
 * WebSearch/WebFetch; local providers get in-process search_web/fetch_url.
 * Mirrors the backend gate (LOCAL_PROVIDERS in llm_bridge/_providers.py plus
 * the claude argv path in adapters/_cli_command.py) — keep the two in sync.
 *
 * Deliberately NOT derived from classifyProvider() (features/settings/
 * components/providerUtils.js) or from constants.js's LOCAL_API_PROVIDERS:
 * both classify providers for other purposes (cli/local-api/cloud-api;
 * whether a time limit applies) and happen to overlap today, but coupling
 * this gate to either would make an unrelated change to those semantics
 * silently change web-tool availability too.
 */
export const WEB_TOOL_PROVIDERS = new Set(['claude', 'ollama', 'omlx', 'llamacpp']);

export function providerSupportsWebTools(providerId) {
  return WEB_TOOL_PROVIDERS.has(providerId);
}
