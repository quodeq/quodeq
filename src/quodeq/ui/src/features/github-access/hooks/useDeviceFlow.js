import { useCallback, useEffect, useRef, useState } from 'react';
import { apiErrorMessage } from '../../../strings/apiErrors.js';
import { DEVICE_FLOW_STATE, FLOW_PHASE } from '../accessVocab.js';

const DEFAULT_POLL_MS = 2000;
const TERMINAL = new Set([DEVICE_FLOW_STATE.DONE, DEVICE_FLOW_STATE.EXPIRED, DEVICE_FLOW_STATE.DENIED, DEVICE_FLOW_STATE.ERROR]);
const IDLE = Object.freeze({ phase: FLOW_PHASE.IDLE, userCode: null, verificationUri: null, login: null, error: null });

/**
 * Drives the GitHub device flow: begin() fetches the user code, then polls
 * the job until it ends. onSignedIn(login) fires once on done.
 */
export function useDeviceFlow({ startDeviceFlow, getDeviceFlow, onSignedIn, pollMs = DEFAULT_POLL_MS }) {
  const [flow, setFlow] = useState(IDLE);
  const timerRef = useRef(null);
  const aliveRef = useRef(true);
  // Generation: begin() and reset() bump it, so work started before them goes stale.
  const runRef = useRef(0);
  // Latest props, so a pending timer never calls a stale callback.
  const latest = useRef({});
  latest.current = { startDeviceFlow, getDeviceFlow, onSignedIn, pollMs };

  const stop = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null;
  }, []);

  useEffect(() => {
    aliveRef.current = true; // StrictMode re-mounts after the cleanup below
    return () => { aliveRef.current = false; stop(); };
  }, [stop]);

  const isStale = (runId) => !aliveRef.current || runId !== runRef.current;

  const poll = useCallback(async (runId) => {
    let status;
    try {
      status = await latest.current.getDeviceFlow();
    } catch (err) {
      console.warn('[useDeviceFlow] poll failed:', err);
      if (!isStale(runId)) setFlow((f) => ({ ...f, phase: FLOW_PHASE.ERROR, error: apiErrorMessage(err, 'githubAccess.pollFailed') }));
      return;
    }
    if (isStale(runId)) return;
    if (TERMINAL.has(status.state)) {
      setFlow((f) => ({ ...f, phase: status.state, login: status.login ?? null, error: status.error ?? null }));
      if (status.state === DEVICE_FLOW_STATE.DONE) latest.current.onSignedIn?.(status.login);
      return;
    }
    timerRef.current = setTimeout(() => poll(runId), latest.current.pollMs);
  }, []);

  const begin = useCallback(async () => {
    stop();
    runRef.current += 1;
    const runId = runRef.current;
    setFlow({ ...IDLE, phase: FLOW_PHASE.STARTING });
    try {
      const code = await latest.current.startDeviceFlow();
      if (isStale(runId)) return;
      setFlow({ ...IDLE, phase: FLOW_PHASE.AWAITING_USER, userCode: code.userCode, verificationUri: code.verificationUri });
      timerRef.current = setTimeout(() => poll(runId), latest.current.pollMs);
    } catch (err) {
      console.warn('[useDeviceFlow] start failed:', err);
      if (!isStale(runId)) setFlow({ ...IDLE, phase: FLOW_PHASE.ERROR, error: apiErrorMessage(err, 'githubAccess.startFailed') });
    }
  }, [poll, stop]);

  const reset = useCallback(() => { stop(); runRef.current += 1; setFlow(IDLE); }, [stop]);

  return { ...flow, begin, reset };
}
