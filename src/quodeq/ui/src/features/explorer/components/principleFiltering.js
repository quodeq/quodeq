import { useMemo } from 'react';
import { usePrincipleData } from './explorerDataHooks.js';
import { useHydratedCompliance, useHydratedFindings } from '../hooks/useHydratedCompliance.js';
import { SEVERITY_FILTER_ALL } from '../../../vocab/severity.js';
import { FINDING_TYPE } from '../../../vocab/findingType.js';
import { countKnownSeverities, emptySeverityLists, normalizeSeverity } from '../../../utils/severity.js';

/** The violations split into one list per severity; anything the vocabulary
 * does not know, or none at all, lands in the unknown bucket (the same
 * normalization the worst-files aggregation applies), never dropped. */
export function bucketBySeverity(violations) {
  const bySeverity = emptySeverityLists();
  for (const v of violations || []) bySeverity[normalizeSeverity(v.severity)].push(v);
  return bySeverity;
}

/** Split an evalPrincipal's violations into per-severity buckets and totals. */
export function computeEvalPrincipleData(evalPrincipal) {
  const { principleData, dimViolations = [], dimCompliance = [] } = evalPrincipal;
  const violations = (principleData?.violations?.length > 0) ? principleData.violations : dimViolations;
  // A deferred /scores item has no reason/snippet yet but is still a real check.
  const compliance = dimCompliance.filter((c) => c.file || c.reason || c.snippet || c.detailDeferred);
  const violationsBySeverity = bucketBySeverity(violations);
  const sevCounts = countKnownSeverities(violations, { ignoreCase: true });
  return { violations, compliance, violationsBySeverity, sevCounts };
}

/** Narrow the per-severity buckets to the active filter (or pass through
 * for 'all'/no filter). */
export function filterBySeveritySelection(filteredBySeverity, activeSevFilter) {
  if (!activeSevFilter || activeSevFilter === SEVERITY_FILTER_ALL) return filteredBySeverity;
  const filtered = {};
  for (const sev of Object.keys(filteredBySeverity)) {
    filtered[sev] = sev === activeSevFilter ? filteredBySeverity[sev] : [];
  }
  return filtered;
}

/**
 * Combines the static evalPrincipal split (computeEvalPrincipleData) with
 * the live dismiss state (usePrincipleData) into the buckets
 * PrincipleDetailPage renders: filtered-by-dismiss, then filtered-by-the
 * active severity selection.
 */
export function usePrincipleFiltering(evalPrincipal, severityFilter, onDismiss) {
  const { violations: slimViolations, compliance: slimCompliance } = useMemo(() => computeEvalPrincipleData(evalPrincipal), [evalPrincipal]);
  // /scores defers reason, snippet, context and links on both kinds; the
  // cards render them, so both lists are hydrated here and the severity
  // buckets are rebuilt from the hydrated rows.
  const violations = useHydratedFindings(slimViolations, FINDING_TYPE.VIOLATION);
  const compliance = useHydratedCompliance(slimCompliance);
  const violationsBySeverity = useMemo(() => bucketBySeverity(violations), [violations]);

  const {
    liveScore, liveGrade, activeSevFilter, setActiveSevFilter,
    handleDismiss, dismissedSet,
  } = usePrincipleData(evalPrincipal, severityFilter, onDismiss);

  const { filteredBySeverity, filteredViolations, liveSevCounts } = useMemo(() => {
    const bySev = {};
    for (const sev of Object.keys(violationsBySeverity)) {
      bySev[sev] = (violationsBySeverity[sev] || []).filter(
        (v) => !dismissedSet.has(`${v.file}:${v.line}`)
      );
    }
    const allFiltered = Object.values(bySev).flat();
    return { filteredBySeverity: bySev, filteredViolations: allFiltered, liveSevCounts: countKnownSeverities(allFiltered, { ignoreCase: true }) };
  }, [violationsBySeverity, dismissedSet]);

  const displayedBySeverity = useMemo(
    () => filterBySeveritySelection(filteredBySeverity, activeSevFilter),
    [filteredBySeverity, activeSevFilter]
  );

  return {
    violations, compliance, violationsBySeverity,
    liveScore, liveGrade, activeSevFilter, setActiveSevFilter,
    handleDismiss, filteredViolations, liveSevCounts, displayedBySeverity,
  };
}
