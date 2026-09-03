import { useState, useEffect, useCallback } from 'react';
import { getUpdateStatus, startSelfUpdate } from '../../api/index.js';

const ACTIVE_PHASES = new Set(['downloading', 'verifying', 'installing', 'relaunching']);

/**
 * Drives the packaged app's update-and-relaunch flow: starts the backend
 * self-update and polls status while a phase is active so the banner can
 * render live progress.
 */
export function useSelfUpdate(status, setStatus) {
  const [starting, setStarting] = useState(false);
  const selfUpdate = status?.self_update || null;
  const phase = selfUpdate?.phase || 'idle';
  const active = ACTIVE_PHASES.has(phase);

  useEffect(() => {
    if (!active) return undefined;
    const id = setInterval(() => {
      getUpdateStatus().then(setStatus).catch(() => {});
    }, 1000);
    return () => clearInterval(id);
  }, [active, setStatus]);

  const begin = useCallback(() => {
    setStarting(true);
    startSelfUpdate()
      .then(() => getUpdateStatus().then(setStatus))
      .catch((e) => console.warn('self-update start failed:', e))
      .finally(() => setStarting(false));
  }, [setStatus]);

  return {
    supported: Boolean(selfUpdate?.supported),
    phase,
    active,
    failed: phase === 'error',
    percent: selfUpdate?.percent ?? 0,
    starting,
    begin,
  };
}
