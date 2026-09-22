import { useProviderLogStream } from '../hooks/useProviderLogStream.js';

const STREAM_PATH = '/api/llamacpp/logs/stream';

/**
 * Live tail of the local llama.cpp server's log.
 * @param {boolean} active - opens the stream while true and closes it when it
 *   goes false, so a hidden panel holds no connection.
 * @returns {{logs: Array, status: string}} `logs` is the rolling buffer the
 *   panel renders; `status` is the stream's connection state.
 */
export function useLlamaCppLogStream(active) {
  return useProviderLogStream(STREAM_PATH, active);
}
