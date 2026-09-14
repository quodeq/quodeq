import { useState, useEffect, useCallback } from 'react';
import { useApi } from '../../api/ApiContext.jsx';

export function useUpdateStatus() {
  const { getUpdateStatus } = useApi();
  const [status, setStatus] = useState(null);
  const refresh = useCallback(() => {
    getUpdateStatus().then(setStatus).catch((e) => console.warn('update status refresh failed:', e));
  }, [getUpdateStatus]);
  useEffect(() => { refresh(); }, [refresh]);
  return { status, refresh, setStatus };
}
