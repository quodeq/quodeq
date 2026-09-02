import { useMemo } from 'react';
import { SEVERITY_ORDER as EVAL_SEVERITY_ORDER } from '../../../utils/formatters.js';
import { usePrincipleData } from './explorerDataHooks.js';

/** Split an evalPrincipal's violations into per-severity buckets and totals. */
export function computeEvalPrincipleData(evalPrincipal) {
  const { principleData, dimViolations = [], dimCompliance = [] } = evalPrincipal;
  const violations = (principleData?.violations?.length > 0) ? principleData.violations : dimViolations;
  const compliance = dimCompliance.filter((c) => c.file || c.reason || c.snippet);
  const violationsBySeverity = {};
  const sevCounts = { critical: 0, major: 0, minor: 0 };
  for (const sev of EVAL_SEVERITY_ORDER) violationsBySeverity[sev] = [];
  for (const v of violations) {
    const sev = (v.severity || 'minor').toLowerCase();
    if (violationsBySeverity[sev]) violationsBySeverity[sev].push(v);
    if (sevCounts[sev] !== undefined) sevCounts[sev]++;
  }
  return { violations, compliance, violationsBySeverity, sevCounts };
}

/** Narrow the per-severity buckets to the active filter (or pass through
 * for 'all'/no filter). */
export function filterBySeveritySelection(filteredBySeverity, activeSevFilter) {
  if (!activeSevFilter || activeSevFilter === 'all') return filteredBySeverity;
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
  const { violations, compliance, violationsBySeverity } = useMemo(() => computeEvalPrincipleData(evalPrincipal), [evalPrincipal]);

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
    const counts = { critical: 0, major: 0, minor: 0 };
    allFiltered.forEach((v) => { const s = (v.severity || 'minor').toLowerCase(); if (counts[s] !== undefined) counts[s]++; });
    return { filteredBySeverity: bySev, filteredViolations: allFiltered, liveSevCounts: counts };
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
