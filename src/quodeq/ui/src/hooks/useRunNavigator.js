import { useState, useEffect } from 'react';

/**
 * Manages run navigation state: current run index, prev/next/latest controls.
 *
 * @param {Object} opts
 * @param {string} opts.selectedRun - Currently selected run ID or 'latest'
 * @param {Array} opts.availableRuns - Array of { runId, dateLabel, ... }
 * @param {Function} opts.onRunChange - Callback when run selection changes
 * @param {Function} opts.onNavigate - Callback to push a page onto the nav stack
 * @returns run navigator state and handlers
 */
export function useRunNavigator({ selectedRun, availableRuns, onRunChange, onNavigate }) {
  const [overviewRunIndex, setOverviewRunIndex] = useState(0);

  useEffect(() => {
    if (!availableRuns.length) return;
    if (selectedRun === 'latest') {
      setOverviewRunIndex(0);
    } else {
      const idx = availableRuns.findIndex((r) => r.runId === selectedRun);
      if (idx >= 0) setOverviewRunIndex(idx);
    }
  }, [selectedRun, availableRuns]);

  const currentOverviewRun = availableRuns[overviewRunIndex]?.runId || 'latest';

  function handleRunPrev() {
    const idx = Math.min(overviewRunIndex + 1, availableRuns.length - 1);
    setOverviewRunIndex(idx);
    onRunChange(availableRuns[idx]?.runId || 'latest');
  }

  function handleRunNext() {
    const idx = Math.max(overviewRunIndex - 1, 0);
    setOverviewRunIndex(idx);
    onRunChange(availableRuns[idx]?.runId || 'latest');
  }

  function handleRunLatest() {
    setOverviewRunIndex(0);
    onRunChange(availableRuns[0]?.runId || 'latest');
  }

  function handleRunView() {
    onNavigate('run', { runId: currentOverviewRun });
  }

  function handleRunSelect(runId) {
    const idx = availableRuns.findIndex((r) => r.runId === runId);
    if (idx >= 0) setOverviewRunIndex(idx);
    onRunChange(runId);
  }

  return {
    overviewRunIndex,
    currentOverviewRun,
    handleRunPrev,
    handleRunNext,
    handleRunLatest,
    handleRunView,
    handleRunSelect,
  };
}
