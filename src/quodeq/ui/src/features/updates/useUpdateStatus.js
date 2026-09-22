import { useState, useEffect, useCallback } from 'react';
import { useApi } from '../../api/ApiContext.jsx';

/**
 * The backend's update status, read once on mount.
 *
 * The setter stays inside: callers get `refresh()` to re-read it, `adopt()`
 * to hand over a status they already fetched (a manual check, a self-update
 * poll), and `setAutoCheck()` for the auto-check toggle's optimistic write.
 */
export function useUpdateStatus() {
  const { getUpdateStatus } = useApi();
  const [status, setStatus] = useState(null);
  const refresh = useCallback(() => {
    getUpdateStatus().then(setStatus).catch((e) => console.warn('update status refresh failed:', e));
  }, [getUpdateStatus]);
  const adopt = useCallback((next) => setStatus(next), []);
  // Local-only: the caller awaits the request and calls this again with the
  // previous value if it fails.
  const setAutoCheck = useCallback((enabled) => {
    setStatus((s) => ({ ...(s || {}), auto_check_enabled: enabled }));
  }, []);
  useEffect(() => { refresh(); }, [refresh]);
  return { status, refresh, adopt, setAutoCheck };
}
