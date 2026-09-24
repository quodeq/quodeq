import { useCallback, useMemo, useState } from 'react';
import { KNOWN_SEVERITIES } from '../../../utils/constants.js';
import { isLowConfidence } from '../../violations/components/LowConfidenceGroup.jsx';
import { FINDING_TYPE } from '../../../vocab/findingType.js';
import { SEVERITY_FILTER_ALL } from '../../../vocab/severity.js';
import { ROW_KIND } from './findingListRows.js';

const dismissKey = (v) => `${v.file}:${v.line}`;

/** Split each severity's live (post-dismiss) bucket into high/low
 * confidence, and total up the counts. */
function computeLiveBuckets(violationsBySeverity, dismissedSet) {
  const low = [];
  const high = {};
  const counts = { critical: 0, major: 0, minor: 0 };
  let total = 0;
  for (const sev of KNOWN_SEVERITIES) {
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

// Header + rows for each severity bucket the active filter lets through.
function pushSeverityRows(arr, { highConfidenceBySeverity, activeFilter }) {
  for (const sev of KNOWN_SEVERITIES) {
    const bucket = highConfidenceBySeverity[sev] || [];
    if (bucket.length === 0) continue;
    if (activeFilter && activeFilter !== SEVERITY_FILTER_ALL && activeFilter !== sev) continue;
    arr.push({ kind: ROW_KIND.SEV_HEADER, sev, count: bucket.length });
    for (const v of bucket) arr.push({ kind: FINDING_TYPE.VIOLATION, v });
  }
}

// The low-confidence toggle, plus its rows when expanded. Suppressed while a
// severity filter is on: the low-confidence split cuts across severities.
function pushLowConfidenceRows(arr, { activeFilter, lowConfidenceViolations, lowConfExpanded }) {
  if (activeFilter && activeFilter !== SEVERITY_FILTER_ALL) return;
  if (lowConfidenceViolations.length === 0) return;
  arr.push({ kind: ROW_KIND.LOW_CONF_TOGGLE, count: lowConfidenceViolations.length, expanded: lowConfExpanded });
  if (!lowConfExpanded) return;
  for (const v of lowConfidenceViolations) arr.push({ kind: ROW_KIND.LOW_CONF_ROW, v });
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
    pushSeverityRows(arr, { highConfidenceBySeverity, activeFilter });
    pushLowConfidenceRows(arr, { activeFilter, lowConfidenceViolations, lowConfExpanded });
  }
  if (showCompliance && totalCompliance > 0) {
    arr.push({ kind: ROW_KIND.COMPLIANCE_HEADER, count: totalCompliance });
    for (const c of compliance) arr.push({ kind: FINDING_TYPE.COMPLIANCE, c });
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
  const distinctSeverities = KNOWN_SEVERITIES.filter((s) => liveSevCounts[s] > 0).length;
  const showFilters = distinctSeverities > 1 || (distinctSeverities >= 1 && totalCompliance > 0);
  const showCompliance = !activeFilter || activeFilter === SEVERITY_FILTER_ALL || activeFilter === FINDING_TYPE.COMPLIANCE;
  const showViolations = activeFilter !== FINDING_TYPE.COMPLIANCE;

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
