/**
 * useDimensionSelection — dimension picking + clean-scan mode + the scan
 * trigger for ReEvaluateCard.
 *
 * buildScanPayload is re-exported from ReEvaluateCard.jsx for its importers.
 * The one-shot clean-scan consumption in handleScan is coupled to onStart's
 * promise chain.
 */
import { useState, useRef, useEffect } from 'react';
import { CLEAN_PERSIST } from '../components/scanModes.js';
import { useDimensionSet } from './useDimensionSet.js';

/**
 * The start-evaluation request body for the selected dimensions, branch,
 * scope and clean-scan mode. `timeLimitS` overrides the provider's configured
 * budget for this run only.
 *
 * @returns {object}
 */
export function buildScanPayload({ info, branch, scopePath, selectedDims, cleanScan, project, timeLimitS }) {
  const payload = { repo: info.path };
  payload.dimensions = [...selectedDims];
  if (branch) payload.branch = branch;
  if (scopePath) payload.scopePath = scopePath;
  payload.cleanScan = cleanScan !== CLEAN_PERSIST.OFF;
  // Per-run budget override (seconds; 0 = no limit). preparePayload treats a
  // present timeLimit as authoritative over the provider's Settings value.
  if (timeLimitS != null) payload.timeLimit = timeLimitS;
  // UI-side bookkeeping (stripped before the HTTP call): lets the
  // in-progress card label itself with the launching project before the
  // backend's report-path marker resolves the job's own project.
  if (project) payload.uiProject = project;
  return payload;
}

// Seed the selection once from the navigation context (e.g. arriving from a
// dimension or principle detail). Runs in an effect rather than the useState
// initializer because the chips (allDimensions) load asynchronously. The ref
// guards it to a single seed per mount so later re-renders never clobber the
// user's own toggles. Ids are matched case-insensitively and only kept when
// they map to a real (visible) chip.
function useSeedPreselectedDims(allDimensions, preselectDims, setSelectedDims) {
  const seededRef = useRef(false);
  useEffect(() => {
    if (seededRef.current) return;
    if (!preselectDims || preselectDims.length === 0) return;
    if (allDimensions.length === 0) return;
    const byLowerId = new Map(allDimensions.map((d) => [String(d.id).toLowerCase(), d.id]));
    const seed = new Set();
    for (const id of preselectDims) {
      const match = byLowerId.get(String(id).toLowerCase());
      if (match) seed.add(match);
    }
    seededRef.current = true;
    if (seed.size > 0) setSelectedDims(seed);
  }, [allDimensions, preselectDims]);
}

/**
 * The re-evaluate card's dimension picker, clean-scan toggle and scan
 * trigger.
 *
 * Scanning with standards available but none selected reports through
 * `onValidationFail` instead of starting. A one-shot clean scan is consumed
 * only once the start actually goes through, so a refused or failed start
 * leaves the toggle armed for the retry.
 */
export function useDimensionSelection({ allDimensions, info, branch, scopePath, onStart, onValidationFail, preselectDims = [], project = null, timeLimitS = null }) {
  const { selectedDims, setSelectedDims, toggleDim, selectAll, clearAll, refuseEmptySelection } = useDimensionSet(allDimensions);
  const [cleanScan, setCleanScan] = useState(CLEAN_PERSIST.OFF);

  useSeedPreselectedDims(allDimensions, preselectDims, setSelectedDims);

  const handleScan = () => {
    if (refuseEmptySelection(onValidationFail)) return;
    const result = onStart(buildScanPayload({ info, branch, scopePath, selectedDims, cleanScan, project, timeLimitS }));
    // Consume the one-shot clean toggle only when the start actually went
    // through. A blocked start (another evaluation running) returns false;
    // a failed start rejects. Eating the toggle in either case makes the
    // user's retry silently run incremental.
    if (cleanScan === CLEAN_PERSIST.ONCE && result !== false) {
      Promise.resolve(result)
        .then(() => setCleanScan(CLEAN_PERSIST.OFF))
        .catch((err) => console.warn('[useDimensionSelection] scan start failed:', err));
    }
  };

  return { selectedDims, toggleDim, selectAll, clearAll, handleScan, cleanScan, setCleanScan };
}
