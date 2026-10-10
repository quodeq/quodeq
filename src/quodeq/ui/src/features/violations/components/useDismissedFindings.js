import { useCallback, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  listDismissedFindings,
  restoreFinding,
  restoreAllFindings,
  deleteFinding,
  deleteAllFindings,
  sharedListDismissedFindings,
} from '../../../api/index.js';
import { applyMutationDelta } from '../../../api/applyMutationDelta.js';
import { projectKeys } from '../../../api/queryKeys.js';
import { confirmDialog } from '../../../utils/confirmDialog.js';
import { t } from '../../../strings/index.js';
import { apiErrorMessage } from '../../../strings/apiErrors.js';
import { PROJECT_SOURCE } from '../../../vocab/projectSource.js';
import { DIALOG_VARIANT } from '../../../vocab/dialogVariant.js';

/**
 * @param {object} options
 * @param {string} options.selectedProject
 * @param {Function} [options.setRestoreError]
 * @param {'local'|'shared'} [options.selectedSource='local'] - Shared projects have no
 *   mutation routes on the backend (dismiss/restore/delete are local-only by
 *   design). When shared, the list reads from the shared-repo mirror endpoint
 *   and every mutation handler below early-returns as a defense-in-depth
 *   no-op — the real gate is the caller passing `undefined` instead of these
 *   handlers to the dismissed sub-tab, but this guard protects against a
 *   handler slipping through some other path and corrupting the local cache
 *   with shared-derived deltas (the local id can collide with a shared id).
 * @param {Function} [options.onReconcile] - The debounced ACTIVE
 *   scheduleDashboardReconcile (see useDashboard.js): the ONE call every
 *   mutation handler below makes on success. It marks the project queries
 *   stale synchronously and then actively refetches after the debounce
 *   window -- restore-all/delete-all return a payload applyMutationDelta's
 *   gates can't patch (scores:null, delta.isLatest:false), and mark-stale
 *   alone never reaches the always-mounted Overview observer.
 *
 * The list lives in the query cache under projectKeys.dismissed, inside the
 * project subtree: the reconcile above refreshes it like every other
 * project query, and a dismiss made anywhere prepends its entry through
 * api/dismissedListCache.js, so the tab shows the finding at once instead
 * of refetching the whole list on a counter bump.
 */
function makeHandleRestore({ selectedProject, isShared, applyDelta, setDismissed, onReconcile, setRestoreError }) {
  return async (d) => {
    if (isShared) return;
    try {
      // The fingerprint names the dismissed entry exactly; the line the
      // listing shows is the finding's current location and may differ from
      // the line the dismissal was recorded at.
      const result = await restoreFinding(selectedProject, {
        req: d.req, file: d.file, line: d.line,
        ...(d.fingerprint ? { fingerprint: d.fingerprint } : {}),
      });
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
      variant: DIALOG_VARIANT.DANGER,
    });
    if (!ok) return;
    try {
      const result = await deleteAllFindings(selectedProject);
      applyDelta(result);
      setDismissed([]);
      onReconcile?.();
    } catch (err) {
      console.error('Failed to delete all findings:', err);
      // CONFIRMATION_REQUIRED carries a `code` (see routes_findings.py) --
      // route through apiErrorMessage so a mapped code shows its translated
      // copy instead of always falling back to the generic fixed message.
      setRestoreError?.(apiErrorMessage(err, 'violations.deleteAllFailed'));
    }
  };
}

/**
 * The project's dismissed list as a query, plus the in-place splice the
 * mutation handlers use: `loading` covers the first fetch, a failed load
 * logs and reports the way the handlers do, and `setDismissed` writes the
 * cached list so a restore or delete shows at once.
 */
function useDismissedList({ selectedProject, selectedSource, setRestoreError }) {
  const queryClient = useQueryClient();
  const isShared = selectedSource === PROJECT_SOURCE.SHARED;
  const query = useQuery({
    queryKey: projectKeys.dismissed(selectedProject, selectedSource),
    queryFn: () => (isShared ? sharedListDismissedFindings : listDismissedFindings)(selectedProject),
    enabled: Boolean(selectedProject),
  });

  // Mirrors the console.error + setRestoreError convention every mutation
  // handler uses -- a failed load used to fall back to [] silently, leaving
  // the user staring at an empty list with no explanation. setRestoreError
  // excluded from the deps: callers don't memoize it.
  useEffect(() => {
    if (!query.error) return;
    console.error('Failed to load dismissed findings:', query.error);
    setRestoreError?.(t('violations.dismissedLoadFailed'));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query.error]);

  const setDismissed = useCallback((next) => {
    queryClient.setQueryData(
      projectKeys.dismissed(selectedProject, selectedSource),
      (prev) => (typeof next === 'function' ? next(prev ?? []) : next),
    );
  }, [queryClient, selectedProject, selectedSource]);

  return {
    dismissed: query.data ?? [],
    loading: Boolean(selectedProject) && query.isPending,
    setDismissed,
  };
}

export function useDismissedFindings({ selectedProject, setRestoreError, selectedSource = PROJECT_SOURCE.LOCAL, onReconcile }) {
  const queryClient = useQueryClient();
  const isShared = selectedSource === PROJECT_SOURCE.SHARED;
  const { dismissed, loading, setDismissed } = useDismissedList({ selectedProject, selectedSource, setRestoreError });

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

  const handleRestore = useCallback(
    makeHandleRestore({ selectedProject, isShared, applyDelta, setDismissed, onReconcile, setRestoreError }),
    [selectedProject, onReconcile, setRestoreError, applyDelta, setDismissed, isShared],
  );

  const handleRestoreAll = useCallback(
    makeHandleRestoreAll({ selectedProject, isShared, dismissedCount: dismissed.length, applyDelta, setDismissed, onReconcile, setRestoreError }),
    [selectedProject, onReconcile, setRestoreError, dismissed.length, applyDelta, setDismissed, isShared],
  );

  const handleDelete = useCallback(
    makeHandleDelete({ selectedProject, isShared, applyDelta, setDismissed, onReconcile, setRestoreError }),
    [selectedProject, onReconcile, setRestoreError, applyDelta, setDismissed, isShared],
  );

  const handleDeleteAll = useCallback(
    makeHandleDeleteAll({ selectedProject, isShared, dismissedCount: dismissed.length, applyDelta, setDismissed, onReconcile, setRestoreError }),
    [selectedProject, onReconcile, setRestoreError, dismissed.length, applyDelta, setDismissed, isShared],
  );

  return { dismissed, loading, handleRestore, handleRestoreAll, handleDelete, handleDeleteAll };
}
