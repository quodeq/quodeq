import { useState } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { apiErrorMessage } from '../../../strings/apiErrors.js';
import { writeString } from '../../../adapters/storage.js';
import { LAST_CLONE_ROOT_STORAGE_KEY } from '../../../constants.js';

/**
 * State + submit handler behind IncompleteSetupCard's "Complete setup" CTA:
 * re-registers a legacy `location: "online"` project with a clone target,
 * which overwrites repository_info.json and turns it into a normal local
 * project. Called unconditionally, before the card's early return, so hook
 * order stays stable whether or not the project needs this flow.
 *
 * `registerProject` comes from useApi() so the card can be tested without
 * hitting fetch.
 */
export function useCompleteSetup({ repoUrl, onComplete }) {
  const { registerProject } = useApi();
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit({ cloneDest, ephemeral }) {
    setSubmitting(true);
    setError(null);
    try {
      const result = await registerProject({ repo: repoUrl, cloneDest, ephemeral });
      if (cloneDest) {
        writeString(LAST_CLONE_ROOT_STORAGE_KEY, cloneDest);
      }
      onComplete?.(result);
    } catch (err) {
      setError(apiErrorMessage(err, 'overview.cloneFailed'));
    } finally {
      setSubmitting(false);
    }
  }

  return { open, setOpen, submitting, error, handleSubmit };
}
