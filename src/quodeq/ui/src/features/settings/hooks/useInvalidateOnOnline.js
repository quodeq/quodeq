import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';

/**
 * Invalidate `queryKey` when `status` transitions into 'online'.
 *
 * A cached models query is an empty list or a previous error while the
 * server is down; nothing refetches it just because the daemon came up.
 * Invalidating on the transition makes the dropdown populate as soon as
 * the status pill flips to green, without a navigation.
 *
 * `queryKey` must be referentially stable (a module-level constant), or
 * the effect re-runs on every render.
 */
export function useInvalidateOnOnline(status, queryKey) {
  const queryClient = useQueryClient();
  const prevStatusRef = useRef(status ?? 'offline');
  useEffect(() => {
    const current = status ?? 'offline';
    if (prevStatusRef.current !== 'online' && current === 'online') {
      queryClient.invalidateQueries({ queryKey });
    }
    prevStatusRef.current = current;
  }, [status, queryClient, queryKey]);
}
