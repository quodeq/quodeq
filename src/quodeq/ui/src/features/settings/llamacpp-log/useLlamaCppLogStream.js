import { useProviderLogStream } from '../hooks/useProviderLogStream.js';

const URL = '/api/llamacpp/logs/stream';

export function useLlamaCppLogStream(active) {
  return useProviderLogStream(URL, active);
}
