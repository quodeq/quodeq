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

  const stop = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null;
  }, []);

  useEffect(() => () => { aliveRef.current = false; stop(); }, [stop]);

  const poll = useCallback(async () => {
    let status;
    try {
      status = await getDeviceFlow();
    } catch (err) {
      if (aliveRef.current) setFlow((f) => ({ ...f, phase: FLOW_PHASE.ERROR, error: apiErrorMessage(err, 'githubAccess.pollFailed') }));
      return;
    }
    if (!aliveRef.current) return;
    if (TERMINAL.has(status.state)) {
      setFlow((f) => ({ ...f, phase: status.state, login: status.login ?? null, error: status.error ?? null }));
      if (status.state === DEVICE_FLOW_STATE.DONE) onSignedIn?.(status.login);
      return;
    }
    timerRef.current = setTimeout(poll, pollMs);
  }, [getDeviceFlow, onSignedIn, pollMs]);

  const begin = useCallback(async () => {
    stop();
    setFlow({ ...IDLE, phase: FLOW_PHASE.STARTING });
    try {
      const code = await startDeviceFlow();
      if (!aliveRef.current) return;
      setFlow({ ...IDLE, phase: FLOW_PHASE.AWAITING_USER, userCode: code.userCode, verificationUri: code.verificationUri });
      timerRef.current = setTimeout(poll, pollMs);
    } catch (err) {
      if (aliveRef.current) setFlow({ ...IDLE, phase: FLOW_PHASE.ERROR, error: apiErrorMessage(err, 'githubAccess.startFailed') });
    }
  }, [startDeviceFlow, poll, pollMs, stop]);

  const reset = useCallback(() => { stop(); setFlow(IDLE); }, [stop]);

  return { ...flow, begin, reset };
}
