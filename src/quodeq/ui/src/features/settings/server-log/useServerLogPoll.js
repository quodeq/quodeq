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

const POLL_MS = 2000;
const MAX_LINES = 5000;
const ISO_TIME_START = 11;
const ISO_TIME_END = 19;

function format(entry) {
  const ts = entry.timestamp ? entry.timestamp.slice(ISO_TIME_START, ISO_TIME_END) : '';
  return ts ? `[${ts}] ${entry.line}` : entry.line;
}

export function useServerLogPoll(active) {
  const [logs, setLogs] = useState([]);
  const sinceRef = useRef(-1);

  // Reset when toggling off; on toggle-on the next queryFn picks up since=-1.
  useEffect(() => {
    if (!active) {
      setLogs([]);
      sinceRef.current = -1;
    } else {
      setLogs([]);
      sinceRef.current = -1;
    }
  }, [active]);

  useQuery({
    queryKey: ['system', 'serverLog'],
    enabled: !!active,
    queryFn: async () => {
      const since = sinceRef.current;
      const url = '/api/logs' + (since >= 0 ? `?since=${since}` : '');
      const r = await fetch(url);
      if (!r.ok) return null;
      const data = await r.json();
      if (!data || !data.lines) return null;
      if (data.lines.length) {
        const formatted = data.lines.map(format);
        setLogs((prev) => {
          const merged = prev.concat(formatted);
          return merged.length > MAX_LINES ? merged.slice(merged.length - MAX_LINES) : merged;
        });
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

  return { logs };
}
