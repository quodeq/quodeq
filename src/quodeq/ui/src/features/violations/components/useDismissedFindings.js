import { useCallback, useEffect, useState } from 'react';
import {
  listDismissedFindings,
  restoreFinding,
  restoreAllFindings,
  deleteFinding,
  deleteAllFindings,
} from '../../../api/index.js';
import { confirmDialog } from '../../../utils/confirmDialog.js';

export function useDismissedFindings(selectedProject, onRefresh, setRestoreError) {
  const [dismissed, setDismissed] = useState([]);

  useEffect(() => {
    if (!selectedProject) return;
    listDismissedFindings(selectedProject).then(setDismissed).catch(() => setDismissed([]));
  }, [selectedProject]);

  const handleRestore = useCallback(async (d) => {
    try {
      await restoreFinding(selectedProject, { req: d.req, file: d.file, line: d.line });
      setDismissed((prev) => prev.filter((item) => !(item.req === d.req && item.file === d.file && item.line === d.line)));
      onRefresh?.();
    } catch (err) {
      console.error('Failed to restore finding:', err);
      setRestoreError?.('Failed to restore finding. Please try again.');
    }
  }, [selectedProject, onRefresh, setRestoreError]);

  const handleRestoreAll = useCallback(async () => {
    try {
      await restoreAllFindings(selectedProject);
      setDismissed([]);
      onRefresh?.();
    } catch (err) {
      console.error('Failed to restore all findings:', err);
      setRestoreError?.('Failed to restore all findings. Please try again.');
    }
  }, [selectedProject, onRefresh, setRestoreError]);

  const handleDelete = useCallback(async (d) => {
    try {
      await deleteFinding(selectedProject, {
        dimension: d.dimension,
        principle: d.principle,
        file: d.file,
      });
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
  }, [selectedProject, onRefresh, setRestoreError]);

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
      await deleteAllFindings(selectedProject);
      setDismissed([]);
      onRefresh?.();
    } catch (err) {
      console.error('Failed to delete all findings:', err);
      setRestoreError?.('Failed to delete all findings. Please try again.');
    }
  }, [selectedProject, onRefresh, setRestoreError, dismissed.length]);

  return { dismissed, handleRestore, handleRestoreAll, handleDelete, handleDeleteAll };
}
