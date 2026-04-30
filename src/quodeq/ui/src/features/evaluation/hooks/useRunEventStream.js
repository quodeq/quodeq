/**
 * SSE-driven replacement for useEvaluation's polling loops.
 *
 * Subscribes to /api/evaluations/<jobId>/events, registers handlers for
 * status / dimension-completed / finding / done events, and exposes the
 * same state shape that useEvaluation consumers already render against.
 *
 * Gated by VITE_USE_SSE_EVENTS (see useEvaluation.js for the switch).
 */
import { useEffect, useRef, useState } from 'react';

export function useRunEventStream(jobId) {
  const [status, setStatus] = useState(null);
  const [completedDimensions, setCompletedDimensions] = useState({});
  const [findings, setFindings] = useState([]);
  const [done, setDone] = useState(false);
  const [connected, setConnected] = useState(false);
  const sourceRef = useRef(null);

  useEffect(() => {
    if (!jobId) return undefined;

    const source = new EventSource(`/api/evaluations/${jobId}/events`);
    sourceRef.current = source;
    setConnected(true);

    source.addEventListener('status', (e) => {
      try {
        setStatus(JSON.parse(e.data));
      } catch {
        // ignore malformed frames; reconnect handles recovery
      }
    });

    source.addEventListener('dimension-completed', (e) => {
      try {
        const data = JSON.parse(e.data);
        setCompletedDimensions((prev) => ({ ...prev, [data.dimension]: data }));
      } catch {
        // ignore
      }
    });

    source.addEventListener('finding', (e) => {
      try {
        const data = JSON.parse(e.data);
        setFindings((prev) => [...prev, data]);
      } catch {
        // ignore
      }
    });

    source.addEventListener('done', () => {
      setDone(true);
      source.close();
      setConnected(false);
    });

    return () => {
      source.close();
      sourceRef.current = null;
      setConnected(false);
    };
  }, [jobId]);

  return { status, completedDimensions, findings, done, connected };
}
