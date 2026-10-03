import { useCallback, useRef, useState } from 'react';
import { apiErrorMessage } from '../../../strings/apiErrors.js';
import { accessFailureFrom } from '../../github-access/accessFailure.js';

/**
 * connect()/pull(): in-flight guards -- aria-disabled on the triggering
 * button does not stop a click in this codebase's convention (buttons stay
 * clickable so their handlers can surface a snackbar/tooltip), and the
 * Enter-key path on TermInput bypasses the button entirely. So double-submit
 * protection has to live here, at the hook, rather than on any one caller's
 * button. Refs (not state) because the guard must be readable synchronously
 * on the very next call, before any state update triggered by this call has
 * committed/re-rendered -- the identical in-flight-ref idiom used by
 * usePublishTrigger (usePublish.js).
 *
 * Both calls only START a background job (the server answers 202); the
 * outcome arrives through the sync status (hooks/useSyncStatus.js), so
 * `connectError` here covers just a failure to start the job. A start refused
 * by the access probe (ACCESS_<KIND>) is kept as `accessFailure` instead, the
 * envelope the access panel renders. `connect` resolves true once the job
 * started (the 202), false when the start was refused or ignored.
 */
export function useSharedActions({ connectShared, startPull }) {
  const [connecting, setConnecting] = useState(false);
  const [connectError, setConnectError] = useState(null);
  const [accessFailure, setAccessFailure] = useState(null);
  const connectingRef = useRef(false);
  const pullingRef = useRef(false);

  const connect = useCallback(async (nextUrl) => {
    if (connectingRef.current) return false; // already starting a connect -- ignore the repeat click/Enter
    connectingRef.current = true;
    setConnecting(true);
    setConnectError(null);
    setAccessFailure(null);
    try {
      await connectShared(nextUrl);
      return true;
    } catch (err) {
      const failure = accessFailureFrom(err);
      if (failure) setAccessFailure(failure);
      else setConnectError(apiErrorMessage(err, 'projects.connectFailed'));
      return false;
    } finally {
      connectingRef.current = false;
      setConnecting(false);
    }
  }, [connectShared]);

  const pull = useCallback(async (projectId, action) => {
    if (pullingRef.current) return; // a pull is already starting -- ignore the repeat click
    pullingRef.current = true;
    try {
      return await startPull(projectId, action);
    } finally {
      pullingRef.current = false;
    }
  }, [startPull]);

  return { connecting, connectError, accessFailure, connect, pull };
}
