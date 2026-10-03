import { useState, useCallback } from 'react';
import { useApi } from '../../api/ApiContext.jsx';
import { useVisibleInterval } from '../../hooks/useVisibleInterval.js';

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
  // A rejected start request never reaches the backend status, so the
  // failure is held here until a fresh status reports a non-error phase.
  const [startFailed, setStartFailed] = useState(false);
  const selfUpdate = status?.self_update || null;
  const phase = selfUpdate?.phase || SELF_UPDATE_PHASE.IDLE;
  const active = ACTIVE_PHASES.has(phase);

  const adopt = useCallback((next) => {
    if ((next?.self_update?.phase || SELF_UPDATE_PHASE.IDLE) !== SELF_UPDATE_PHASE.ERROR) setStartFailed(false);
    adoptStatus(next);
  }, [adoptStatus]);

  useVisibleInterval(() => {
    getUpdateStatus().then(adopt).catch((e) => console.warn('self-update status poll failed:', e));
  }, active ? STATUS_POLL_MS : 0);

  const begin = useCallback(() => {
    setStarting(true);
    setStartFailed(false);
    startSelfUpdate()
      .then(() => getUpdateStatus().then(adopt))
      .catch((e) => {
        console.warn('self-update start failed:', e);
        setStartFailed(true);
      })
      .finally(() => setStarting(false));
  }, [adopt, getUpdateStatus, startSelfUpdate]);

  return {
    supported: Boolean(selfUpdate?.supported),
    phase,
    active,
    failed: phase === SELF_UPDATE_PHASE.ERROR || startFailed,
    percent: selfUpdate?.percent ?? 0,
    starting,
    begin,
  };
}
