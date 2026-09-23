import { useState, useEffect, useCallback } from 'react';
import { useApi } from '../../api/ApiContext.jsx';

// The self-update flow's own phase vocabulary, not the run/job/dim
// vocabulary -- kept local rather than forced into vocab/*.js.
const SELF_UPDATE_PHASE = Object.freeze({
  IDLE: 'idle', DOWNLOADING: 'downloading', VERIFYING: 'verifying',
  INSTALLING: 'installing', RELAUNCHING: 'relaunching', ERROR: 'error',
});
const ACTIVE_PHASES = new Set([
  SELF_UPDATE_PHASE.DOWNLOADING, SELF_UPDATE_PHASE.VERIFYING,
  SELF_UPDATE_PHASE.INSTALLING, SELF_UPDATE_PHASE.RELAUNCHING,
]);
// Fast enough that the phase/percent banner reads as live progress.
const STATUS_POLL_MS = 1000;

/**
 * Drives the packaged app's update-and-relaunch flow: starts the backend
 * self-update and polls status while a phase is active so the banner can
 * render live progress. `adoptStatus` takes each freshly fetched status.
 */
export function useSelfUpdate(status, adoptStatus) {
  const { getUpdateStatus, startSelfUpdate } = useApi();
  const [starting, setStarting] = useState(false);
  const selfUpdate = status?.self_update || null;
  const phase = selfUpdate?.phase || SELF_UPDATE_PHASE.IDLE;
  const active = ACTIVE_PHASES.has(phase);

  useEffect(() => {
    if (!active) return undefined;
    const id = setInterval(() => {
      getUpdateStatus().then(adoptStatus).catch((e) => console.warn('self-update status poll failed:', e));
    }, STATUS_POLL_MS);
    return () => clearInterval(id);
  }, [active, adoptStatus, getUpdateStatus]);

  const begin = useCallback(() => {
    setStarting(true);
    startSelfUpdate()
      .then(() => getUpdateStatus().then(adoptStatus))
      .catch((e) => console.warn('self-update start failed:', e))
      .finally(() => setStarting(false));
  }, [adoptStatus, getUpdateStatus, startSelfUpdate]);

  return {
    supported: Boolean(selfUpdate?.supported),
    phase,
    active,
    failed: phase === SELF_UPDATE_PHASE.ERROR,
    percent: selfUpdate?.percent ?? 0,
    starting,
    begin,
  };
}
