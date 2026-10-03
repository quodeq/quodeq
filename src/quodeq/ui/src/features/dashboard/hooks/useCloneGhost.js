import { useCallback } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { useCloneStatus } from '../../../hooks/useCloneStatus.js';
import { useDismissedCloneFailure } from './useDismissedCloneFailure.js';

const PATH_SEPARATOR = /[/\\][^/\\]*$/;

// The folder a working copy lives in: the clone destination without its last
// segment. Plain string work, the browser has no `path` module.
function parentFolder(dest) {
  if (typeof dest !== 'string' || !PATH_SEPARATOR.test(dest)) return null;
  return dest.replace(PATH_SEPARATOR, '') || null;
}

/**
 * The ghost tile on the Repositories tab: the clone slot while it runs, or
 * while it failed and was not closed. Retry re-posts the same repo into the
 * same parent folder; a 409 (a clone already runs) or any other refusal is
 * ignored because the slot itself shows what is happening.
 *
 * @returns {{ slot: (Object|null), active: boolean, onRetry: () => Promise<void>, onClose: () => void }}
 *   `slot` is null when there is no tile to show.
 */
export function useCloneGhost() {
  const { registerProject } = useApi();
  const clone = useCloneStatus();
  const { dismissed, dismiss } = useDismissedCloneFailure(clone.failed ? clone.slot : null);
  const slot = clone.slot;
  const onRetry = useCallback(async () => {
    const cloneDest = parentFolder(slot?.dest);
    try {
      await registerProject({ repo: slot.repo, ...(cloneDest ? { cloneDest } : {}) });
    } catch (err) {
      // The slot shows the outcome; the log is for the console only.
      console.warn('[useCloneGhost] retry was refused:', err);
    }
  }, [registerProject, slot]);
  const show = clone.active || (clone.failed && !dismissed);
  return { slot: show ? slot : null, active: clone.active, onRetry, onClose: dismiss };
}
