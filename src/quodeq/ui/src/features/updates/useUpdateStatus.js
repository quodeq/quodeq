import { useState, useEffect, useCallback } from 'react';
import { getUpdateStatus } from '../../api/index.js';

export function useUpdateStatus() {
  const [status, setStatus] = useState(null);
  const refresh = useCallback(() => {
    getUpdateStatus().then(setStatus).catch(() => {});
  }, []);
  useEffect(() => { refresh(); }, [refresh]);
  return { status, refresh, setStatus };
}
