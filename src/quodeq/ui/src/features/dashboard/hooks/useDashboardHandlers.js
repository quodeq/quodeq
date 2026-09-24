import { useMemo } from 'react';
import { NAV_TAB } from '../../../vocab/navTab.js';

/**
 * The Overview's navigation callbacks (dimension card, accumulated dimension,
 * file), memoized so the cards do not re-render on every parent render.
 *
 * Each is a no-op without an `onNavigate`, so the page renders fine read-only.
 */
export function useDashboardHandlers(onNavigate, dashboard) {
  return useMemo(() => ({
    handleDimensionCardClick: (item, runId) => {
      if (!onNavigate) return;
      const dateLabel = dashboard?.selectedRun?.dateLabel || item.fromDateLabel;
      onNavigate(NAV_TAB.EXPLORER, { dimension: item.dimension, runId: runId || item.fromRunId, dateLabel, fromProject: item.fromProject });
    },
    handleAccumulatedDimensionClick: (item) => {
      if (onNavigate) onNavigate(NAV_TAB.EXPLORER, { dimension: item.dimension, runId: item.fromRunId, dateLabel: item.fromDateLabel, fromProject: item.fromProject });
    },
    handleFileClick: (fileObj) => { if (onNavigate) onNavigate('file', { file: fileObj }); },
  }), [onNavigate, dashboard]);
}
