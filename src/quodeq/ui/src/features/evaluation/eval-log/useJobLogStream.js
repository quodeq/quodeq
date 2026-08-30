import { useEffect, useRef, useState } from 'react';
import { t } from '../../../strings/index.js';

const MAX_LINES = 5000;
const READYSTATE_CLOSED = 2;
const INACTIVITY_MS = 60000;

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
  const inactivityRef = useRef(null);

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
    if (inactivityRef.current != null) {
      clearTimeout(inactivityRef.current);
      inactivityRef.current = null;
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

    const resetInactivity = () => {
      if (inactivityRef.current != null) {
        clearTimeout(inactivityRef.current);
      }
      inactivityRef.current = setTimeout(() => {
        es.close();
        setStatus('error');
      }, INACTIVITY_MS);
    };

    resetInactivity();

    // Set once the stream reaches ANY terminal outcome ('done' fired, or
    // unmount/jobId-switch tore this effect down). Guards es.onerror: closing
    // an EventSource can itself dispatch a trailing error event in some
    // browsers, which must not overwrite a clean 'done' with status='error'
    // (or, post-teardown, update state on an effect that already cleaned up).
    let finished = false;

    es.onmessage = (e) => {
      resetInactivity();
      append(e.data);
    };
    es.addEventListener('done', (e) => {
      finished = true;
      if (inactivityRef.current != null) {
        clearTimeout(inactivityRef.current);
        inactivityRef.current = null;
      }
      const state = (e?.data || '').trim().toLowerCase();
      // The rendered terminal line is EvalLogProvider's job now (it reads
      // terminalState + logPresentation.terminalLine); this hook only
      // records which state was reached.
      setTerminalState(state || 'done');
      setStatus('done');
      es.close();
    });
    es.onerror = () => {
      if (finished) return;
      if (es.readyState === READYSTATE_CLOSED) {
        append(t('evaluate.logDisconnected'));
        setStatus('error');
      }
    };

    return () => {
      finished = true;
      es.close();
      if (inactivityRef.current != null) {
        clearTimeout(inactivityRef.current);
        inactivityRef.current = null;
      }
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
