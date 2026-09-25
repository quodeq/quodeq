import { useState } from 'react';
import { apiErrorMessage } from '../../../strings/apiErrors.js';
import { useSidePane } from '../../side-pane/SidePaneContext.jsx';
import { HTTP_STATUS } from '../../../constants.js';

/**
 * Pull-to-local (shared-only cards): mirrors the delete-confirm idiom for
 * the 409 same-uuid collision case.
 */
export function usePullToLocal({ shared, onProjectsReload }) {
  const { showToast } = useSidePane();
  const [pullConflictId, setPullConflictId] = useState(null);
  const [pulledIds, setPulledIds] = useState(() => new Set());

  // Record the pull and reload the local list. Without the reload, a project
  // pulled here never appears in the merged list until some unrelated action
  // happens to reload the project list -- the user has no way to tell the
  // pull actually landed a local copy.
  async function markPulled(id) {
    setPulledIds((prev) => new Set(prev).add(id));
    await onProjectsReload?.();
  }

  async function handlePull(id) {
    try {
      await shared.pull(id);
      setPullConflictId(null);
      await markPulled(id);
    } catch (err) {
      if (err?.status === HTTP_STATUS.CONFLICT) {
        setPullConflictId(id);
      } else {
        showToast(apiErrorMessage(err, 'projects.pullFailed'));
      }
    }
  }

  async function handleConfirmCopy(id) {
    try {
      await shared.pull(id, 'copy');
      await markPulled(id);
    } catch (err) {
      showToast(apiErrorMessage(err, 'projects.pullFailed'));
    } finally {
      setPullConflictId(null);
    }
  }

  return {
    pullConflictId,
    pulledIds,
    handlePull,
    handleConfirmCopy,
    cancelConflict: () => setPullConflictId(null),
  };
}
