import { useCallback, useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  listDismissedFindings,
  restoreFinding,
  restoreAllFindings,
  deleteFinding,
  deleteAllFindings,
  sharedListDismissedFindings,
} from '../../../api/index.js';
import { applyMutationDelta } from '../../../api/applyMutationDelta.js';
import { confirmDialog } from '../../../utils/confirmDialog.js';
import { t } from '../../../strings/index.js';

/**
 * @param {string} selectedProject
 * @param {Function} [onRefresh] - Unused by the mutation handlers (the
 *   reconcile below marks stale itself); kept in the signature for the
 *   navigation-time mount refresh ViolationsPage wires separately.
 * @param {Function} [setRestoreError]
 * @param {number} [refreshKey=0]
 * @param {'local'|'shared'} [selectedSource='local'] - Shared projects have no
 *   mutation routes on the backend (dismiss/restore/delete are local-only by
 *   design). When shared, the list reads from the shared-repo mirror endpoint
 *   and every mutation handler below early-returns as a defense-in-depth
 *   no-op — the real gate is the caller passing `undefined` instead of these
 *   handlers to the dismissed sub-tab, but this guard protects against a
 *   handler slipping through some other path and corrupting the local cache
 *   with shared-derived deltas (the local id can collide with a shared id).
 * @param {Function} [onReconcile] - The debounced ACTIVE
 *   scheduleDashboardReconcile (see useDashboard.js): the ONE call every
 *   mutation handler below makes on success. It marks the project queries
 *   stale synchronously and then actively refetches after the debounce
 *   window -- restore-all/delete-all return a payload applyMutationDelta's
 *   gates can't patch (scores:null, delta.isLatest:false), and mark-stale
 *   alone never reaches the always-mounted Overview observer.
 */
function makeHandleRestore({ selectedProject, isShared, applyDelta, setDismissed, onReconcile, setRestoreError }) {
  return async (d) => {
    if (isShared) return;
    try {
      const result = await restoreFinding(selectedProject, { req: d.req, file: d.file, line: d.line });
      applyDelta(result);
      setDismissed((prev) => prev.filter((item) => !(item.req === d.req && item.file === d.file && item.line === d.line)));
      onReconcile?.();
    } catch (err) {
      console.error('Failed to restore finding:', err);
      setRestoreError?.(t('violations.restoreFailed'));
    }
  };
}

// Restoring un-suppresses every finding the user ever triaged away, and the
// only undo is dismissing them again one by one. The button sits next to the
// per-item Restore, so a mis-click is cheap to make and expensive to reverse.
// Delete-all has always confirmed; this needs it at least as much.
function makeHandleRestoreAll({ selectedProject, isShared, dismissedCount, applyDelta, setDismissed, onReconcile, setRestoreError }) {
  return async () => {
    if (isShared) return;
    const ok = await confirmDialog({
      title: t('violations.restoreDismissedTitle'),
      message: t('violations.restoreDismissedBody', { count: dismissedCount }),
      confirmLabel: t('violations.restoreAll'),
    });
    if (!ok) return;
    try {
      const result = await restoreAllFindings(selectedProject);
      applyDelta(result);
      setDismissed([]);
      onReconcile?.();
    } catch (err) {
      console.error('Failed to restore all findings:', err);
      setRestoreError?.(t('violations.restoreAllFailed'));
    }
  };
}

function makeHandleDelete({ selectedProject, isShared, applyDelta, setDismissed, onReconcile, setRestoreError }) {
  return async (d) => {
    if (isShared) return;
    try {
      const result = await deleteFinding(selectedProject, {
        dimension: d.dimension,
        principle: d.principle,
        file: d.file,
      });
      applyDelta(result);
      // Sweep every dismissed entry that shares the same (dimension, principle, file),
      // matching the backend sweep so the local list stays in sync without a refetch.
      setDismissed((prev) => prev.filter((item) => !(
        item.dimension === d.dimension
        && item.principle === d.principle
        && item.file === d.file
      )));
      onReconcile?.();
    } catch (err) {
      console.error('Failed to delete finding:', err);
      setRestoreError?.(t('violations.deleteFailed'));
    }
  };
}

function makeHandleDeleteAll({ selectedProject, isShared, dismissedCount, applyDelta, setDismissed, onReconcile, setRestoreError }) {
  return async () => {
    if (isShared) return;
    const ok = await confirmDialog({
      title: t('violations.deleteDismissedTitle'),
      message: t('violations.deleteDismissedBody', { count: dismissedCount }),
      confirmLabel: 'Delete',
      cancelLabel: 'Cancel',
      variant: 'danger',
    });
    if (!ok) return;
    try {
      const result = await deleteAllFindings(selectedProject);
      applyDelta(result);
      setDismissed([]);
      onReconcile?.();
    } catch (err) {
      console.error('Failed to delete all findings:', err);
      setRestoreError?.(t('violations.deleteAllFailed'));
    }
  };
}

export function useDismissedFindings(selectedProject, onRefresh, setRestoreError, refreshKey = 0, selectedSource = 'local', onReconcile) {
  const [dismissed, setDismissed] = useState([]);
  const queryClient = useQueryClient();
  const isShared = selectedSource === 'shared';

  // Fold the mutation-delta from a restore/delete response into the React Query
  // caches so dimension scores/grades update instantly and the run-detail
  // violation lists get invalidated for a lazy refetch. Additive — the local
  // setDismissed splices and the onReconcile calls below still run.
  const applyDelta = useCallback((result) => {
    const delta = result?.delta;
    if (!delta) return;
    applyMutationDelta(queryClient, selectedProject, {
      ...delta,
      dimensions: result?.scores?.dimensions,
    });
  }, [queryClient, selectedProject]);

  // refreshKey lets the parent force a refetch when something dismissed an
  // entry elsewhere (e.g. the principle-detail page). Without it, the
  // dismissed sub-tab only fetched on mount, so dismisses made on other
  // pages never appeared until the user switched projects.
  useEffect(() => {
    if (!selectedProject) return;
    const fetchDismissed = isShared ? sharedListDismissedFindings : listDismissedFindings;
    fetchDismissed(selectedProject).then(setDismissed).catch(() => setDismissed([]));
  }, [selectedProject, refreshKey, isShared]);

  const handleRestore = useCallback(
    makeHandleRestore({ selectedProject, isShared, applyDelta, setDismissed, onReconcile, setRestoreError }),
    [selectedProject, onReconcile, setRestoreError, applyDelta, isShared],
  );

  const handleRestoreAll = useCallback(
    makeHandleRestoreAll({ selectedProject, isShared, dismissedCount: dismissed.length, applyDelta, setDismissed, onReconcile, setRestoreError }),
    [selectedProject, onReconcile, setRestoreError, dismissed.length, applyDelta, isShared],
  );

  const handleDelete = useCallback(
    makeHandleDelete({ selectedProject, isShared, applyDelta, setDismissed, onReconcile, setRestoreError }),
    [selectedProject, onReconcile, setRestoreError, applyDelta, isShared],
  );

  const handleDeleteAll = useCallback(
    makeHandleDeleteAll({ selectedProject, isShared, dismissedCount: dismissed.length, applyDelta, setDismissed, onReconcile, setRestoreError }),
    [selectedProject, onReconcile, setRestoreError, dismissed.length, applyDelta, isShared],
  );

  return { dismissed, handleRestore, handleRestoreAll, handleDelete, handleDeleteAll };
}
