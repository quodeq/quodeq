import { useMemo, useEffect, useRef } from 'react';
import { readVisibleStandardIds } from '../utils/visibleStandards.js';
import { bucketKey } from '../utils/dailyGrouping.js';

/**
 * Filters dailyRuns to those where at least one visible standard dimension
 * was evaluated. Resets selectedRun to 'latest' whenever the visible set
 * changes to a non-empty result.
 *
 * @param granularity - period granularity ('day' | 'week' | 'month'); determines
 *   which period buckets are considered visible, matching the chart's bucketing.
 */
export function useVisibleRuns(dailyRuns, dashboard, activePage, setSelectedRun, granularity = 'day') {
  const visibleDailyRuns = useMemo(() => {
    const visibleSet = new Set(readVisibleStandardIds());
    const trendEntries = dashboard?.trend || [];
    // Build set of period buckets where at least one visible dimension was evaluated
    const visibleDates = new Set();
    for (const entry of trendEntries) {
      if ((entry.dimensions || []).some((d) => visibleSet.has(d.toLowerCase()))) {
        visibleDates.add(bucketKey(entry.dateISO, granularity));
      }
    }
    const trendByRunId = new Map(trendEntries.map((t) => [t.runId, t]));
    return dailyRuns.filter((run) => {
      const bucket = bucketKey(trendByRunId.get(run.runId)?.dateISO, granularity);
      return visibleDates.has(bucket);
    });
  }, [dailyRuns, dashboard, activePage, granularity]);

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
