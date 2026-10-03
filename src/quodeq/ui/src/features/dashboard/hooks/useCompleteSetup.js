import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { projectsKeys } from '../../../api/queryKeys.js';
import { useCloneStatus } from '../../../hooks/useCloneStatus.js';
import { apiErrorMessage } from '../../../strings/apiErrors.js';
import { writeString } from '../../../adapters/storage.js';
import { LAST_CLONE_ROOT_STORAGE_KEY } from '../../../constants.js';

const FALLBACK_KEY = 'overview.cloneFailed';

/**
 * Follows a clone job the submit started (a 202): acts once on the terminal
 * edge of the slot for `following.repo` whose finishedAt is new (not the one
 * cached before the post). DONE completes, ERROR shows the mapped message;
 * either way the follow ends and `submitting` drops.
 */
function useFollowClone({ following, setFollowing, setSubmitting, setError, onComplete }) {
  const clone = useCloneStatus();
  useEffect(() => {
    const { slot } = clone;
    if (!following || !slot || slot.repo !== following.repo || !(clone.done || clone.failed)) return;
    if (slot.finishedAt === following.stale) return;
    setFollowing(null);
    setSubmitting(false);
    if (clone.done) onComplete?.(slot);
    else setError(apiErrorMessage({ code: slot.code, message: slot.error }, FALLBACK_KEY));
    // Keyed on the slot and the follow alone: the setters are stable.
  }, [following, clone.slot]);
  return clone.slot;
}

/**
 * State + submit handler behind IncompleteSetupCard's "Complete setup" CTA:
 * re-registers a legacy `location: "online"` project with a clone target,
 * which overwrites repository_info.json and turns it into a normal local
 * project. A folder registers synchronously (200) and completes at once; a
 * url clones as a background job (202) that this hook follows through the
 * shared clone slot, staying `submitting` until it lands. The card mounts
 * it only for a project that needs this flow.
 *
 * `registerProject` comes from useApi() so the card can be tested without
 * hitting fetch.
 */
export function useCompleteSetup({ repoUrl, onComplete }) {
  const { registerProject } = useApi();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [following, setFollowing] = useState(null);
  const slot = useFollowClone({ following, setFollowing, setSubmitting, setError, onComplete });

  async function handleSubmit({ cloneDest, ephemeral }) {
    // The slot as it stood before this post: its finishedAt is an earlier job's.
    const stale = slot?.finishedAt ?? null;
    setSubmitting(true);
    setError(null);
    let started = false;
    try {
      const result = await registerProject({ repo: repoUrl, cloneDest, ephemeral });
      if (cloneDest) writeString(LAST_CLONE_ROOT_STORAGE_KEY, cloneDest);
      started = Boolean(result?.started);
      if (!started) { onComplete?.(result); return; }
      setFollowing({ repo: result.repo || repoUrl, stale });
      // Wakes the app-level poller (slow while idle) so the edge arrives at once.
      queryClient.invalidateQueries({ queryKey: projectsKeys.clone() })
        .catch((err) => console.warn('[useCompleteSetup] clone status refetch failed:', err));
    } catch (err) {
      setError(apiErrorMessage(err, FALLBACK_KEY));
    } finally {
      if (!started) setSubmitting(false);
    }
  }

  return { open, setOpen, submitting, error, handleSubmit };
}
