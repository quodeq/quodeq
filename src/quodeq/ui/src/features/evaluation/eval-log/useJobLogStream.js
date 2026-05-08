import { useEffect, useRef, useState } from 'react';

const MAX_LINES = 5000;
const READYSTATE_CLOSED = 2;

const TERMINAL_STATE_LINE = {
  cancelled: '── evaluation cancelled ──',
  failed: '── evaluation failed ──',
  lost: '── evaluation lost ──',
  done: '── evaluation complete ──',
  complete: '── evaluation complete ──',
  completed: '── evaluation complete ──',
};

export function useJobLogStream(jobId) {
  const [logs, setLogs] = useState([]);
  const [status, setStatus] = useState('idle');
  const [terminalState, setTerminalState] = useState(null);
  // Coalesce bursts of SSE messages into one render per frame. Each `onmessage`
  // is its own task, so without batching a chatty stream commits N times in
  // 16ms — which means N reconciliations of the entire log list.
  const pendingRef = useRef([]);
  const rafRef = useRef(null);
  const timerRef = useRef(null);

  useEffect(() => {
    setLogs([]);
    setTerminalState(null);
    pendingRef.current = [];
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    if (timerRef.current != null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    if (!jobId) {
      setStatus('idle');
      return undefined;
    }
    setStatus('streaming');
    const url = `/api/jobs/${encodeURIComponent(jobId)}/logs/stream`;
    const es = new EventSource(url);

    const flush = () => {
      if (rafRef.current != null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      if (timerRef.current != null) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      const batch = pendingRef.current;
      if (batch.length === 0) return;
      pendingRef.current = [];
      setLogs((prev) => {
        const merged = prev.length === 0 ? batch.slice() : prev.concat(batch);
        if (merged.length > MAX_LINES) {
          return merged.slice(merged.length - MAX_LINES);
        }
        return merged;
      });
    };
    const append = (line) => {
      pendingRef.current.push(line);
      // Schedule both a rAF (for smooth in-frame batching while visible) and
      // a timer fallback. Browsers throttle rAF to 0 when the tab is hidden,
      // so without the timer the queue would never drain in background tabs.
      // Whichever fires first runs flush; the other becomes a no-op.
      if (rafRef.current == null) {
        rafRef.current = requestAnimationFrame(flush);
      }
      if (timerRef.current == null) {
        timerRef.current = setTimeout(flush, 50);
      }
    };

    es.onmessage = (e) => append(e.data);
    es.addEventListener('done', (e) => {
      const state = (e?.data || '').trim().toLowerCase();
      append(TERMINAL_STATE_LINE[state] || '── evaluation complete ──');
      setTerminalState(state || 'done');
      setStatus('done');
      es.close();
    });
    es.onerror = () => {
      if (es.readyState === READYSTATE_CLOSED) {
        append('── stream disconnected ──');
        setStatus('error');
      }
    };

    return () => {
      es.close();
      if (rafRef.current != null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      if (timerRef.current != null) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      pendingRef.current = [];
    };
  }, [jobId]);

  return { logs, status, terminalState };
}
