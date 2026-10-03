import { useCallback } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { useCloneStatus } from '../../../hooks/useCloneStatus.js';
import { CLONE_CODE_PROJECT_EXISTS } from '../../../api/projectClone.js';
import { useDismissedCloneFailure } from './useDismissedCloneFailure.js';

/**
 * The ghost tile on the Repositories tab: the clone slot while it runs, or
 * while it failed and was not closed. A PROJECT_EXISTS end is no failure to
 * show: the analyze panel resumes and launches the existing project. Retry
 * re-posts the same repo without a cloneDest, so the server uses its default
 * root (an explicit root the first request named is not in the slot); a 409
 * (a clone already runs) or any other refusal is ignored because the slot
 * itself shows what is happening.
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
    try {
      await registerProject({ repo: slot.repo });
    } catch (err) {
      // The slot shows the outcome; the log is for the console only.
      console.warn('[useCloneGhost] retry was refused:', err);
    }
  }, [registerProject, slot]);
  const exists = slot?.code === CLONE_CODE_PROJECT_EXISTS;
  const show = clone.active || (clone.failed && !exists && !dismissed);
  return { slot: show ? slot : null, active: clone.active, onRetry, onClose: dismiss };
}
