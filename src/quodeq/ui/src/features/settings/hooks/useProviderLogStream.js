/**
 * Server-log SSE stream shared by the local-provider log panels.
 *
 * Ollama and llama.cpp both expose their server log as an SSE endpoint with
 * the same frame shape, so the subscription, the line buffer and the terminal
 * states live here and each provider only names its URL.
 */
import { useEffect, useState } from 'react';
import { EMPTY_LOG_BUFFER, LOG_BUFFER_MAX_LINES, appendLines, clearLines } from '../../../utils/logBuffer.js';

// EventSource.CLOSED — an onerror at any other readyState is a reconnect the
// browser handles itself, not a failure worth surfacing.
const READYSTATE_CLOSED = 2;

/**
 * Subscribe to a provider's log stream while `active`.
 *
 * Resets to an empty log whenever it is switched off or the URL changes, and
 * closes the connection on unmount.
 *
 * @param {string} url SSE endpoint serving the provider's log lines.
 * @param {boolean} active Whether the panel is open and should be streaming.
 * @returns {{logs: string[], firstSeq: number, status: 'idle'|'streaming'|'done'|'error'}}
 *   `firstSeq` is the sequence number of `logs[0]` (see utils/logBuffer.js).
 */
export function useProviderLogStream(url, active) {
  const [buf, setBuf] = useState(EMPTY_LOG_BUFFER);
  const [status, setStatus] = useState('idle');

  useEffect(() => {
    setBuf(clearLines);
    if (!active) {
      setStatus('idle');
      return undefined;
    }
    setStatus('streaming');
    const es = new EventSource(url);

    es.onmessage = (e) => {
      setBuf((prev) => appendLines(prev, [e.data], LOG_BUFFER_MAX_LINES));
    };
    es.addEventListener('done', () => {
      setStatus('done');
      es.close();
    });
    es.onerror = () => {
      if (es.readyState === READYSTATE_CLOSED) setStatus('error');
    };

    return () => { es.close(); };
  }, [url, active]);

  return { logs: buf.lines, firstSeq: buf.firstSeq, status };
}
