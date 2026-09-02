import { useState } from 'react';
import { t } from '../../../strings/index.js';

// Pull-to-local (shared-only cards): mirrors the delete-confirm idiom for
// the 409 same-uuid collision case.
export function usePullToLocal({ shared, onProjectsReload }) {
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
        alert(t('projects.pullFailed', { message: err?.message || t('history.unknownError') }));
      }
    }
  }

  async function handleConfirmCopy(id) {
    try {
      await shared.pull(id, 'copy');
      setPulledIds((prev) => new Set(prev).add(id));
      await onProjectsReload?.();
    } catch (err) {
      alert(t('projects.pullFailed', { message: err?.message || t('history.unknownError') }));
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
