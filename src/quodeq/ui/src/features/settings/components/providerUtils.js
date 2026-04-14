// These markers must stay in sync with the backend's _LOCAL_API_MARKERS
// in quodeq/llm_bridge/_providers.py (configurable via QUODEQ_LOCAL_API_MARKERS).
const LOCAL_MARKERS = ['11434', 'localhost', '127.0.0.1', 'ollama'];

export function classifyProvider(id, type, config) {
  if (type === 'cli' || !type) return 'cli';
  const apiBase = (config?.api_base || '').toLowerCase();
  if (LOCAL_MARKERS.some((m) => apiBase.includes(m))) return 'local-api';
  return 'cloud-api';
}
