const LOCAL_MARKERS = ['11434', 'localhost', '127.0.0.1', 'ollama'];

export function classifyProvider(id, type, config) {
  if (type === 'cli' || !type) return 'cli';
  const apiBase = (config?.api_base || '').toLowerCase();
  if (LOCAL_MARKERS.some((m) => apiBase.includes(m))) return 'local-api';
  return 'cloud-api';
}
