import { useCallback, useRef, useState } from 'react';
import { sharedKeys } from '../../../api/queryKeys.js';
import { apiErrorMessage } from '../../../strings/apiErrors.js';

// connect()/pull(): in-flight guards -- aria-disabled on the triggering
// button does not stop a click in this codebase's convention (buttons stay
// clickable so their handlers can surface a snackbar/tooltip), and the
// Enter-key path on TermInput bypasses the button entirely. So double-submit
// protection has to live here, at the hook, rather than on any one caller's
// button. Refs (not state) because the guard must be readable synchronously
// on the very next call, before any state update triggered by this call has
// committed/re-rendered -- the identical in-flight-ref idiom used by
// usePublishTrigger (usePublish.js). Extracted verbatim from
// useSharedProjects.js.
export function useSharedActions({ connectShared, pullSharedProject, queryClient }) {
  const [connecting, setConnecting] = useState(false);
  const [connectError, setConnectError] = useState(null);
  const connectingRef = useRef(false);
  const pullingRef = useRef(false);

  const connect = useCallback(async (nextUrl) => {
    if (connectingRef.current) return; // already connecting -- ignore the repeat click/Enter
    connectingRef.current = true;
    setConnecting(true);
    setConnectError(null);
    try {
      await connectShared(nextUrl);
      // Invalidate everything "shared"-prefixed, not just status: a
      // reconnect to a DIFFERENT url while already configured=true would
      // otherwise never re-fetch the list (its `enabled` flag never
      // toggles, since configured was already true before and after).
      await queryClient.invalidateQueries({ queryKey: sharedKeys.all() });
    } catch (err) {
      setConnectError(apiErrorMessage(err, 'projects.connectFailed'));
    } finally {
      connectingRef.current = false;
      setConnecting(false);
    }
  }, [connectShared, queryClient]);

  const pull = useCallback(async (projectId, action) => {
    if (pullingRef.current) return; // a pull is already in flight -- ignore the repeat click
    pullingRef.current = true;
    try {
      const result = await pullSharedProject(projectId, action);
      queryClient.invalidateQueries({ queryKey: sharedKeys.list() });
      return result;
    } finally {
      pullingRef.current = false;
    }
  }, [pullSharedProject, queryClient]);

  return { connecting, connectError, connect, pull };
}
