import { useCallback, useEffect, useState } from 'react';
import { listDismissedFindings, restoreFinding, restoreAllFindings } from '../../../api/index.js';

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

  return { dismissed, handleRestore, handleRestoreAll };
}
