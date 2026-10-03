// Display names for the providers the wizard can name, keyed by the
// server's provider id (the one ACTIVE_PROVIDER_KEY stores). Product names,
// not copy. One copy for the provider step and the analyze screen.
/* eslint-disable i18n/no-prose-literals */
export const PROVIDER_LABELS = Object.freeze({
  claude: 'Claude Code',
  codex: 'Codex CLI',
  gemini: 'Gemini CLI',
  copilot: 'GitHub Copilot',
  ollama: 'Ollama',
  openrouter: 'OpenRouter',
  openai: 'OpenAI',
  anthropic: 'Anthropic',
});
/* eslint-enable i18n/no-prose-literals */

// The detection probes name two CLIs differently from the server's
// ai_providers.json ids; every other probe id is already the server's.
const CLI_SERVER_ID = Object.freeze({ 'codex-cli': 'codex', 'claude-code': 'claude' });

/**
 * The server's provider id for a detection probe id (or a server id, unchanged).
 *
 * @param {string} id
 * @returns {string}
 */
export function serverProviderId(id) {
  return CLI_SERVER_ID[id] || id;
}

/**
 * The display name for a provider, by server or detection id; an unknown id
 * reads as itself.
 *
 * @param {string|null} id
 * @returns {string|null}
 */
export function providerLabel(id) {
  if (!id) return null;
  const serverId = serverProviderId(id);
  return PROVIDER_LABELS[serverId] || serverId;
}
