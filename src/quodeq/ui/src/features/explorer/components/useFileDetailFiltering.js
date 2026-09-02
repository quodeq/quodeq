import { useCallback, useMemo, useState } from 'react';
import { SEVERITY_ORDER } from '../../../utils/formatters.js';
import { isLowConfidence } from '../../violations/components/LowConfidenceGroup.jsx';

const dismissKey = (v) => `${v.file}:${v.line}`;

/** Split each severity's live (post-dismiss) bucket into high/low
 * confidence, and total up the counts. */
function computeLiveBuckets(violationsBySeverity, dismissedSet) {
  const low = [];
  const high = {};
  const counts = { critical: 0, major: 0, minor: 0 };
  let total = 0;
  for (const sev of SEVERITY_ORDER) {
    const bucket = (violationsBySeverity?.[sev] || []).filter((v) => !dismissedSet.has(dismissKey(v)));
    const highBucket = [];
    for (const v of bucket) {
      if (isLowConfidence(v)) low.push(v);
      else highBucket.push(v);
    }
    high[sev] = highBucket;
    if (counts[sev] !== undefined) counts[sev] = bucket.length;
    total += bucket.length;
  }
  return { lowConfidenceViolations: low, highConfidenceBySeverity: high, liveSevCounts: counts, liveTotal: total };
}

// Flatten everything into a single virtualizable items array. Mixing
// headers + rows in one list lets us virtualize the whole page with one
// scroller; React never holds more than ~30 row instances at once even on
// 3k-violation projects.
function buildFileDetailItems({
  showViolations, showCompliance, activeFilter, highConfidenceBySeverity,
  lowConfidenceViolations, lowConfExpanded, compliance, totalCompliance,
}) {
  const arr = [];
  if (showViolations) {
    for (const sev of SEVERITY_ORDER) {
      const bucket = highConfidenceBySeverity[sev] || [];
      if (bucket.length === 0) continue;
      if (activeFilter && activeFilter !== 'all' && activeFilter !== sev) continue;
      arr.push({ kind: 'sev-header', sev, count: bucket.length });
      for (const v of bucket) arr.push({ kind: 'violation', v });
    }
    if ((!activeFilter || activeFilter === 'all') && lowConfidenceViolations.length > 0) {
      arr.push({ kind: 'low-conf-toggle', count: lowConfidenceViolations.length, expanded: lowConfExpanded });
      if (lowConfExpanded) {
        for (const v of lowConfidenceViolations) arr.push({ kind: 'low-conf-row', v });
      }
    }
  }
  if (showCompliance && totalCompliance > 0) {
    arr.push({ kind: 'compliance-header', count: totalCompliance });
    for (const c of compliance) arr.push({ kind: 'compliance', c });
  }
  return arr;
}

/**
 * Dismiss state + the live (post-dismiss) severity buckets, low-confidence
 * split, and the flattened virtualizable items array FileDetailPage renders.
 */
export function useFileDetailFiltering({ file, onDismiss, activeFilter, lowConfExpanded }) {
  const [dismissedSet, setDismissedSet] = useState(new Set());

  const handleDismiss = useCallback((v) => {
    if (!onDismiss) return;
    onDismiss(v);
    setDismissedSet((prev) => new Set(prev).add(dismissKey(v)));
  }, [onDismiss]);

  const { lowConfidenceViolations, highConfidenceBySeverity, liveSevCounts, liveTotal } = useMemo(
    () => computeLiveBuckets(file.violationsBySeverity, dismissedSet),
    [file.violationsBySeverity, dismissedSet],
  );

  const totalCompliance = file.compliance?.length || 0;
  const distinctSeverities = SEVERITY_ORDER.filter((s) => liveSevCounts[s] > 0).length;
  const showFilters = distinctSeverities > 1 || (distinctSeverities >= 1 && totalCompliance > 0);
  const showCompliance = !activeFilter || activeFilter === 'all' || activeFilter === 'compliance';
  const showViolations = activeFilter !== 'compliance';

  const items = useMemo(
    () => buildFileDetailItems({
      showViolations, showCompliance, activeFilter, highConfidenceBySeverity,
      lowConfidenceViolations, lowConfExpanded, compliance: file.compliance, totalCompliance,
    }),
    [showViolations, showCompliance, activeFilter, highConfidenceBySeverity, lowConfidenceViolations, lowConfExpanded, file.compliance, totalCompliance],
  );

  return {
    dismissedSet, handleDismiss, liveSevCounts, liveTotal,
    totalCompliance, showFilters, items,
  };
}
