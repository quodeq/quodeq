import { useEffect, useState } from 'react';

const URL = '/api/llamacpp/logs/stream';
const MAX_LINES = 5000;

export function useLlamaCppLogStream(active) {
  const [logs, setLogs] = useState([]);
  const [status, setStatus] = useState('idle');

  useEffect(() => {
    if (!active) {
      setLogs([]);
      setStatus('idle');
      return undefined;
    }
    setLogs([]);
    setStatus('streaming');
    const es = new EventSource(URL);

    es.onmessage = (e) => {
      setLogs((prev) => {
        const next = prev.length >= MAX_LINES ? prev.slice(prev.length - MAX_LINES + 1) : prev;
        return [...next, e.data];
      });
    };
    es.addEventListener('done', () => {
      setStatus('done');
      es.close();
    });
    es.onerror = () => {
      const READYSTATE_CLOSED = 2;
      if (es.readyState === READYSTATE_CLOSED) setStatus('error');
    };

    return () => { es.close(); };
  }, [active]);

  return { logs, status };
}
