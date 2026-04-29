import { useEffect, useRef, useState } from 'react';

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

  useEffect(() => {
    if (!active) {
      setLogs([]);
      sinceRef.current = -1;
      return undefined;
    }
    setLogs([]);
    sinceRef.current = -1;
    let cancelled = false;
    let timer = null;

    function tick() {
      const url = '/api/logs' + (sinceRef.current >= 0 ? `?since=${sinceRef.current}` : '');
      fetch(url)
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => {
          if (cancelled || !data || !data.lines) return;
          if (data.lines.length) {
            const formatted = data.lines.map(format);
            setLogs((prev) => {
              const merged = prev.concat(formatted);
              return merged.length > MAX_LINES ? merged.slice(merged.length - MAX_LINES) : merged;
            });
            sinceRef.current = data.lines[data.lines.length - 1].index;
          }
          if (!cancelled) timer = setTimeout(tick, POLL_MS);
        })
        .catch(() => { if (!cancelled) timer = setTimeout(tick, POLL_MS); });
    }
    tick();

    return () => { cancelled = true; if (timer) clearTimeout(timer); };
  }, [active]);

  return { logs };
}
