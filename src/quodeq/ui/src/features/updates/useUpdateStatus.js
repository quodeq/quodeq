import { useState, useEffect, useCallback } from 'react';
import { useApi } from '../../api/ApiContext.jsx';

export function useUpdateStatus() {
  const { getUpdateStatus } = useApi();
  const [status, setStatus] = useState(null);
  const refresh = useCallback(() => {
    getUpdateStatus().then(setStatus).catch(() => {});
  }, [getUpdateStatus]);
  useEffect(() => { refresh(); }, [refresh]);
  return { status, refresh, setStatus };
}
