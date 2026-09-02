/**
 * useDimensionSelection — dimension picking + clean-scan mode + the scan
 * trigger for ReEvaluateCard.
 *
 * Split out of ReEvaluateCard.jsx verbatim, including buildScanPayload
 * (re-exported from ReEvaluateCard.jsx so `from './ReEvaluateCard.jsx'`
 * importers, including the test, keep working unchanged). The one-shot
 * clean-scan consumption in handleScan is coupled to onStart's promise
 * chain — left exactly as it was.
 */
import { useState, useRef, useEffect } from 'react';
import { t } from '../../../strings/index.js';

const NO_STANDARDS_MESSAGE = t('evaluate.noStandardsMessage');

export function buildScanPayload({ info, branch, scopePath, selectedDims, cleanScan, project, timeLimitS }) {
  const payload = { repo: info.path };
  payload.dimensions = [...selectedDims];
  if (branch) payload.branch = branch;
  if (scopePath) payload.scopePath = scopePath;
  payload.cleanScan = cleanScan !== 'off';
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

export function useDimensionSelection(allDimensions, info, branch, scopePath, onStart, onValidationFail, preselectDims = [], project = null, timeLimitS = null) {
  const [selectedDims, setSelectedDims] = useState(new Set());
  const [cleanScan, setCleanScan] = useState('off');

  useSeedPreselectedDims(allDimensions, preselectDims, setSelectedDims);

  const toggleDim = (id) => {
    setSelectedDims((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const selectAll = () => setSelectedDims(new Set(allDimensions.map((d) => d.id)));
  const clearAll = () => setSelectedDims(new Set());
  const handleScan = () => {
    if (allDimensions.length > 0 && selectedDims.size === 0) {
      onValidationFail?.(NO_STANDARDS_MESSAGE);
      return;
    }
    const result = onStart(buildScanPayload({ info, branch, scopePath, selectedDims, cleanScan, project, timeLimitS }));
    // Consume the one-shot clean toggle only when the start actually went
    // through. A blocked start (another evaluation running) returns false;
    // a failed start rejects. Eating the toggle in either case makes the
    // user's retry silently run incremental.
    if (cleanScan === 'once' && result !== false) {
      Promise.resolve(result).then(
        () => setCleanScan('off'),
        () => {},
      );
    }
  };

  return { selectedDims, toggleDim, selectAll, clearAll, handleScan, cleanScan, setCleanScan };
}
