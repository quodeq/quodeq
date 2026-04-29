import { useEffect, useRef, useState } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';

const POLL_MS = 5000;

export function useOllamaServerStatus() {
  const { getOllamaStatus } = useApi();
  const [state, setState] = useState(null);
  const timerRef = useRef(null);

  useEffect(() => {
    let cancelled = false;

    function tick() {
      getOllamaStatus()
        .then((data) => {
          if (cancelled) return;
          if (data?.running) {
            setState({ status: 'online', address: data.address ?? null });
          } else {
            setState({ status: 'offline', address: null });
          }
        })
        .catch(() => {
          if (!cancelled) setState({ status: 'offline', address: null });
        });
    }
    tick();
    timerRef.current = setInterval(tick, POLL_MS);
    return () => {
      cancelled = true;
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [getOllamaStatus]);

  return state;
}
