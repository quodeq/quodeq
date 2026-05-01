import { useEffect, useState } from 'react';

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

  useEffect(() => {
    setLogs([]);
    setTerminalState(null);
    if (!jobId) {
      setStatus('idle');
      return undefined;
    }
    setStatus('streaming');
    const url = `/api/jobs/${encodeURIComponent(jobId)}/logs/stream`;
    const es = new EventSource(url);

    function append(line) {
      setLogs((prev) => {
        if (prev.length >= MAX_LINES) {
          return [...prev.slice(prev.length - MAX_LINES + 1), line];
        }
        return [...prev, line];
      });
    }

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
    };
  }, [jobId]);

  return { logs, status, terminalState };
}
