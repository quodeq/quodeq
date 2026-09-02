import { useEffect, useRef, useState } from 'react';
import { t } from '../../../strings/index.js';

const MAX_LINES = 5000;
const READYSTATE_CLOSED = 2;
const INACTIVITY_MS = 60000;

function clearRef(ref, canceller) {
  if (ref.current != null) {
    canceller(ref.current);
    ref.current = null;
  }
}

// Coalesce bursts of SSE messages into one render per frame. Each `onmessage`
// is its own task, so without batching a chatty stream commits N times in
// 16ms — which means N reconciliations of the entire log list.
function makeFlush({ rafRef, timerRef, pendingRef, setLogs }) {
  return () => {
    clearRef(rafRef, cancelAnimationFrame);
    clearRef(timerRef, clearTimeout);
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
}

function makeAppend({ pendingRef, rafRef, timerRef, flush }) {
  return (line) => {
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
}

function makeResetInactivity({ inactivityRef, es, setStatus }) {
  return () => {
    if (inactivityRef.current != null) {
      clearTimeout(inactivityRef.current);
    }
    inactivityRef.current = setTimeout(() => {
      es.close();
      setStatus('error');
    }, INACTIVITY_MS);
  };
}

function wireEventSource({ es, append, resetInactivity, inactivityRef, setTerminalState, setStatus, finishedBox }) {
  es.onmessage = (e) => {
    resetInactivity();
    append(e.data);
  };
  es.addEventListener('done', (e) => {
    finishedBox.current = true;
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
    if (finishedBox.current) return;
    if (es.readyState === READYSTATE_CLOSED) {
      append(t('evaluate.logDisconnected'));
      setStatus('error');
    }
  };
}

function teardownStream({ es, finishedBox, inactivityRef, rafRef, timerRef, pendingRef }) {
  finishedBox.current = true;
  es.close();
  clearRef(inactivityRef, clearTimeout);
  clearRef(rafRef, cancelAnimationFrame);
  clearRef(timerRef, clearTimeout);
  pendingRef.current = [];
}

export function useJobLogStream(jobId) {
  const [logs, setLogs] = useState([]);
  const [status, setStatus] = useState('idle');
  const [terminalState, setTerminalState] = useState(null);
  const pendingRef = useRef([]);
  const rafRef = useRef(null);
  const timerRef = useRef(null);
  const inactivityRef = useRef(null);

  useEffect(() => {
    setLogs([]);
    setTerminalState(null);
    pendingRef.current = [];
    clearRef(rafRef, cancelAnimationFrame);
    clearRef(timerRef, clearTimeout);
    clearRef(inactivityRef, clearTimeout);
    if (!jobId) {
      setStatus('idle');
      return undefined;
    }
    setStatus('streaming');
    const url = `/api/jobs/${encodeURIComponent(jobId)}/logs/stream`;
    const es = new EventSource(url);

    const flush = makeFlush({ rafRef, timerRef, pendingRef, setLogs });
    const append = makeAppend({ pendingRef, rafRef, timerRef, flush });
    const resetInactivity = makeResetInactivity({ inactivityRef, es, setStatus });
    resetInactivity();

    // Set once the stream reaches ANY terminal outcome ('done' fired, or
    // unmount/jobId-switch tore this effect down). Guards es.onerror: closing
    // an EventSource can itself dispatch a trailing error event in some
    // browsers, which must not overwrite a clean 'done' with status='error'
    // (or, post-teardown, update state on an effect that already cleaned up).
    const finishedBox = { current: false };

    wireEventSource({ es, append, resetInactivity, inactivityRef, setTerminalState, setStatus, finishedBox });

    return () => teardownStream({ es, finishedBox, inactivityRef, rafRef, timerRef, pendingRef });
  }, [jobId]);

  return { logs, status, terminalState };
}
