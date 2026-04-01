import { useMemo, useEffect, useRef } from 'react';
import { readVisibleStandardIds } from '../utils/visibleStandards.js';

/**
 * Filters dailyRuns to those where at least one visible standard dimension
 * was evaluated. Resets selectedRun to 'latest' whenever the visible set
 * changes to a non-empty result.
 */
export function useVisibleRuns(dailyRuns, dashboard, activePage, setSelectedRun) {
  const visibleDailyRuns = useMemo(() => {
    const visibleSet = new Set(readVisibleStandardIds());
    const trendEntries = dashboard?.trend || [];
    // Build set of dates where at least one visible dimension was evaluated
    const visibleDates = new Set();
    for (const entry of trendEntries) {
      if ((entry.dimensions || []).some((d) => visibleSet.has(d.toLowerCase()))) {
        visibleDates.add((entry.dateISO || '').slice(0, 10));
      }
    }
    const trendByRunId = new Map(trendEntries.map((t) => [t.runId, t]));
    return dailyRuns.filter((run) => {
      const datePart = (trendByRunId.get(run.runId)?.dateISO || '').slice(0, 10);
      return visibleDates.has(datePart);
    });
  }, [dailyRuns, dashboard, activePage]);

  const visibleRunIdsKey = visibleDailyRuns.map((r) => r.runId).join(',');
  const prevRunIdsKeyRef = useRef(visibleRunIdsKey);
  useEffect(() => {
    // Only reset when the visible runs actually change content (not when transitioning through empty during project switch)
    if (prevRunIdsKeyRef.current !== visibleRunIdsKey && visibleRunIdsKey !== '' && prevRunIdsKeyRef.current !== '') {
      setSelectedRun('latest');
    }
    if (visibleRunIdsKey !== '') {
      prevRunIdsKeyRef.current = visibleRunIdsKey;
    }
  }, [visibleRunIdsKey, setSelectedRun]);

  return visibleDailyRuns;
}
