import { useState, useEffect, useRef } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';

const POLL_MS = 5000;

export default function ServerStatus() {
  const { getOllamaStatus } = useApi();
  const [status, setStatus] = useState(null);
  const timerRef = useRef(null);

  useEffect(() => {
    function tick() {
      getOllamaStatus()
        .then(setStatus)
        .catch(() => setStatus({ running: false, error: 'Could not reach server' }));
    }
    tick();
    timerRef.current = setTimeout(function schedule() {
      tick();
      timerRef.current = setTimeout(schedule, POLL_MS);
    }, POLL_MS);
    return () => clearTimeout(timerRef.current);
  }, []);

  if (!status) return null;

  if (status.running) {
    return (
      <div className="server-status server-status--online">
        <span className="server-dot server-dot--online" />
        <span>Server running</span>
        <span className="server-address">{status.address}</span>
      </div>
    );
  }

  return (
    <div className="server-status server-status--offline">
      <span className="server-dot server-dot--offline" />
      <span>Server offline — Run <code>ollama serve</code> or open the Ollama app</span>
    </div>
  );
}
