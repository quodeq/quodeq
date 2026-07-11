import { useCallback, useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  listDismissedFindings,
  restoreFinding,
  restoreAllFindings,
  deleteFinding,
  deleteAllFindings,
} from '../../../api/index.js';
import { applyMutationDelta } from '../../../api/applyMutationDelta.js';
import { confirmDialog } from '../../../utils/confirmDialog.js';

export function useDismissedFindings(selectedProject, onRefresh, setRestoreError, refreshKey = 0) {
  const [dismissed, setDismissed] = useState([]);
  const queryClient = useQueryClient();

  // Fold the mutation-delta from a restore/delete response into the React Query
  // caches so dimension scores/grades update instantly and the run-detail
  // violation lists get invalidated for a lazy refetch. Additive — the local
  // setDismissed splices and onRefresh below still run.
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
    listDismissedFindings(selectedProject).then(setDismissed).catch(() => setDismissed([]));
  }, [selectedProject, refreshKey]);

  const handleRestore = useCallback(async (d) => {
    try {
      const result = await restoreFinding(selectedProject, { req: d.req, file: d.file, line: d.line });
      applyDelta(result);
      setDismissed((prev) => prev.filter((item) => !(item.req === d.req && item.file === d.file && item.line === d.line)));
      onRefresh?.();
    } catch (err) {
      console.error('Failed to restore finding:', err);
      setRestoreError?.('Failed to restore finding. Please try again.');
    }
  }, [selectedProject, onRefresh, setRestoreError, applyDelta]);

  const handleRestoreAll = useCallback(async () => {
    try {
      const result = await restoreAllFindings(selectedProject);
      applyDelta(result);
      setDismissed([]);
      onRefresh?.();
    } catch (err) {
      console.error('Failed to restore all findings:', err);
      setRestoreError?.('Failed to restore all findings. Please try again.');
    }
  }, [selectedProject, onRefresh, setRestoreError, applyDelta]);

  const handleDelete = useCallback(async (d) => {
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
      onRefresh?.();
    } catch (err) {
      console.error('Failed to delete finding:', err);
      setRestoreError?.('Failed to delete finding. Please try again.');
    }
  }, [selectedProject, onRefresh, setRestoreError, applyDelta]);

  const handleDeleteAll = useCallback(async () => {
    const count = dismissed.length;
    const ok = await confirmDialog({
      title: 'Delete dismissed findings?',
      message: `Are you sure you want to permanently delete those ${count} findings? This cannot be undone.`,
      confirmLabel: 'Delete',
      cancelLabel: 'Cancel',
      variant: 'danger',
    });
    if (!ok) return;
    try {
      const result = await deleteAllFindings(selectedProject);
      applyDelta(result);
      setDismissed([]);
      onRefresh?.();
    } catch (err) {
      console.error('Failed to delete all findings:', err);
      setRestoreError?.('Failed to delete all findings. Please try again.');
    }
  }, [selectedProject, onRefresh, setRestoreError, dismissed.length, applyDelta]);

  return { dismissed, handleRestore, handleRestoreAll, handleDelete, handleDeleteAll };
}
