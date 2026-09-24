/**
 * Server-log SSE stream shared by the local-provider log panels.
 *
 * Ollama and llama.cpp both expose their server log as an SSE endpoint with
 * the same frame shape, so the subscription, the line buffer and the terminal
 * states live here and each provider only names its URL.
 */
import { useEffect, useState } from 'react';
import { LOG_STREAM_STATUS } from '../../../vocab/logStreamStatus.js';

// Keep the tail of the log only: the panel is a viewer, not an archive, and
// an unbounded array would grow without limit on a chatty server.
const MAX_LINES = 5000;
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
 * @returns {{logs: string[], status: 'idle'|'streaming'|'done'|'error'}}
 */
export function useProviderLogStream(url, active) {
  const [logs, setLogs] = useState([]);
  const [status, setStatus] = useState(LOG_STREAM_STATUS.IDLE);

  useEffect(() => {
    if (!active) {
      setLogs([]);
      setStatus(LOG_STREAM_STATUS.IDLE);
      return undefined;
    }
    setLogs([]);
    setStatus(LOG_STREAM_STATUS.STREAMING);
    const es = new EventSource(url);

    es.onmessage = (e) => {
      setLogs((prev) => {
        const next = prev.length >= MAX_LINES ? prev.slice(prev.length - MAX_LINES + 1) : prev;
        return [...next, e.data];
      });
    };
    es.addEventListener('done', () => {
      setStatus(LOG_STREAM_STATUS.DONE);
      es.close();
    });
    es.onerror = () => {
      if (es.readyState === READYSTATE_CLOSED) setStatus(LOG_STREAM_STATUS.ERROR);
    };

    return () => { es.close(); };
  }, [url, active]);

  return { logs, status };
}
