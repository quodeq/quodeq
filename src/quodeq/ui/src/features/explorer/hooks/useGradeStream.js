import { useEffect, useState } from 'react';

/**
 * Subscribes to the per-run SSE stream and surfaces the latest `scores.updated`
 * payload.
 *
 * Returns { payload, status, isStale } where:
 *   - payload: the parsed scores.updated event body (same shape as /scores response), or null
 *   - status: 'idle' | 'streaming' | 'error'
 *   - isStale: true when the connection has dropped (UI may show a stale indicator)
 *
 * Gated by VITE_USE_LIVE_GRADES — when not 'true', the hook is a no-op (status='idle').
 * Pass { project, runId } — project is accepted for call-site symmetry but the SSE
 * endpoint is keyed by runId only (/api/evaluations/<runId>/events), matching the
 * existing useRunEventStream URL pattern.
 */
export function useGradeStream({ project: _project, runId }) {
  const [payload, setPayload] = useState(null);
  const [status, setStatus] = useState('idle');
  const [isStale, setIsStale] = useState(false);

  useEffect(() => {
    if (!runId) {
      setPayload(null);
      setStatus('idle');
      setIsStale(false);
      return undefined;
    }
    if (import.meta.env.VITE_USE_LIVE_GRADES !== 'true') {
      setStatus('idle');
      return undefined;
    }

    setStatus('streaming');
    setIsStale(false);

    // URL matches the existing per-run SSE endpoint used by useRunEventStream.
    // See src/features/evaluation/hooks/useRunEventStream.js and
    // src/quodeq/api/_run_events_routes.py — the route is /api/evaluations/<job_id>/events.
    const es = new EventSource(`/api/evaluations/${runId}/events`);

    es.addEventListener('scores.updated', (e) => {
      try {
        const data = JSON.parse(e.data);
        setPayload(data);
        setIsStale(false);
      } catch (_err) {
        // Ignore malformed payloads; keep prior payload visible.
      }
    });

    es.onerror = () => {
      const CLOSED = 2;
      if (es.readyState === CLOSED) {
        setStatus('error');
        setIsStale(true);
      }
    };

    return () => { es.close(); };
  }, [runId]);

  return { payload, status, isStale };
}
