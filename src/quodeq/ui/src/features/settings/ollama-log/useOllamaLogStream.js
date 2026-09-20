import { useProviderLogStream } from '../hooks/useProviderLogStream.js';

const URL = '/api/ollama/logs/stream';

export function useOllamaLogStream(active) {
  return useProviderLogStream(URL, active);
}
