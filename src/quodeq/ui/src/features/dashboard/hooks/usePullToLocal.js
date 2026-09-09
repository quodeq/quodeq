import { useState } from 'react';
import { apiErrorMessage } from '../../../strings/apiErrors.js';
import { useSidePane } from '../../side-pane/SidePaneContext.jsx';

// Pull-to-local (shared-only cards): mirrors the delete-confirm idiom for
// the 409 same-uuid collision case.
export function usePullToLocal({ shared, onProjectsReload }) {
  const { showToast } = useSidePane();
  const [pullConflictId, setPullConflictId] = useState(null);
  const [pulledIds, setPulledIds] = useState(() => new Set());

  async function handlePull(id) {
    try {
      await shared.pull(id);
      setPullConflictId(null);
      setPulledIds((prev) => new Set(prev).add(id));
      // Without this, a project pulled here never appears in the merged list
      // until some unrelated action happens to reload the project list --
      // the user has no way to tell the pull actually landed a local copy.
      await onProjectsReload?.();
    } catch (err) {
      if (err?.status === 409) {
        setPullConflictId(id);
      } else {
        showToast(apiErrorMessage(err, 'projects.pullFailed'));
      }
    }
  }

  async function handleConfirmCopy(id) {
    try {
      await shared.pull(id, 'copy');
      setPulledIds((prev) => new Set(prev).add(id));
      await onProjectsReload?.();
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
