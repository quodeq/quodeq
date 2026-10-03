/**
 * useServerLogPoll — TanStack Query poll for /api/logs.
 *
 * Polls every 2s while `active` is true. The `since` cursor lives in a ref
 * so the queryKey stays stable (and the refetchInterval ticks regularly);
 * it is read inside the queryFn and advanced on each successful response.
 * Toggling `active` resets buffered logs and the cursor.
 */
import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getServerLogs } from '../../../api/serverLog.js';
import { EMPTY_LOG_BUFFER, LOG_BUFFER_MAX_LINES, appendLines, clearLines } from '../../../utils/logBuffer.js';

const POLL_MS = 2000;
// A poll that has not answered after this many intervals is abandoned, so a
// hung backend cannot pin the query in flight and stall every later tick.
const SERVER_LOG_FETCH_TIMEOUT_POLLS = 3;
const SERVER_LOG_FETCH_TIMEOUT_MS = SERVER_LOG_FETCH_TIMEOUT_POLLS * POLL_MS;
const ISO_TIME_START = 11;
const ISO_TIME_END = 19;

function format(entry) {
  const ts = entry.timestamp ? entry.timestamp.slice(ISO_TIME_START, ISO_TIME_END) : '';
  return ts ? `[${ts}] ${entry.line}` : entry.line;
}

export function useServerLogPoll(active) {
  const [buf, setBuf] = useState(EMPTY_LOG_BUFFER);
  const sinceRef = useRef(-1);

  // Reset whenever `active` toggles; on toggle-on the next queryFn picks up
  // since=-1. Both branches were identical, so the reset is unconditional.
  useEffect(() => {
    setBuf(clearLines);
    sinceRef.current = -1;
  }, [active]);

  useQuery({
    queryKey: ['system', 'serverLog'],
    enabled: !!active,
    // TanStack's signal aborts the in-flight poll on unmount or disable.
    queryFn: async ({ signal }) => {
      let data;
      try {
        data = await getServerLogs(sinceRef.current, { signal, timeout: SERVER_LOG_FETCH_TIMEOUT_MS });
      } catch (err) {
        // An HTTP error status carries err.status. It needs its own trace or
        // it is indistinguishable from "no new log lines." A network failure
        // or timeout has no status and fails the query (retried next tick).
        if (err?.status === undefined) throw err;
        console.warn(`Server log poll failed: HTTP ${err.status}`);
        return null;
      }
      if (!data || !data.lines) return null;
      if (data.lines.length) {
        const formatted = data.lines.map(format);
        setBuf((prev) => appendLines(prev, formatted, LOG_BUFFER_MAX_LINES));
        sinceRef.current = data.lines[data.lines.length - 1].index;
      }
      // Return a tick value so TanStack treats the query as fresh data
      // (avoids dedupe/stale-cache surprises across re-renders).
      return { at: Date.now(), count: data.lines.length };
    },
    refetchInterval: POLL_MS,
    refetchOnWindowFocus: false,
    // Swallow fetch errors silently — original implementation just retried.
    retry: false,
  });

  return { logs: buf.lines, firstSeq: buf.firstSeq };
}
