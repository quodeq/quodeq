import { useState, useEffect } from 'react';
import { getOllamaStatus } from '../../../api/index.js';

export default function ServerStatus() {
  const [status, setStatus] = useState(null);

  useEffect(() => {
    getOllamaStatus().then(setStatus).catch(() => setStatus({ running: false, error: 'Could not reach server' }));
    const interval = setInterval(() => {
      getOllamaStatus().then(setStatus).catch(() => setStatus({ running: false, error: 'Connection lost' }));
    }, 15000);
    return () => clearInterval(interval);
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
