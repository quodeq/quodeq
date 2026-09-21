import { useProviderLogStream } from '../hooks/useProviderLogStream.js';

const STREAM_PATH = '/api/ollama/logs/stream';

/**
 * Live tail of the local Ollama server's log.
 * @param {boolean} active - opens the stream while true and closes it when it
 *   goes false, so a hidden panel holds no connection.
 * @returns {{logs: Array, status: string}} `logs` is the rolling buffer the
 *   panel renders; `status` is the stream's connection state.
 */
export function useOllamaLogStream(active) {
  return useProviderLogStream(STREAM_PATH, active);
}
