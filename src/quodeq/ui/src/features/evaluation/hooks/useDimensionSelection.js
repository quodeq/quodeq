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

// The ids of *wanted* that map to a real (visible) chip, matched
// case-insensitively.
function matchVisible(allDimensions, wanted) {
  const byLowerId = new Map(allDimensions.map((d) => [String(d.id).toLowerCase(), d.id]));
  const seed = new Set();
  for (const id of wanted) {
    const match = byLowerId.get(String(id).toLowerCase());
    if (match) seed.add(match);
  }
  return seed;
}

// Seed the selection once: from the navigation context when it carries one
// (e.g. arriving from a dimension or principle detail), else from the
// project's last finished run. Runs in an effect because the chips
// (allDimensions) and the project info load asynchronously; it never seeds
// after the user has touched the selection, so a late answer cannot clobber
// their own picks. Returns whether the seed came from the last run.
function useSeedPreselectedDims({ allDimensions, preselectDims, fallbackDims, setSelectedDims, touched }) {
  const seededRef = useRef(false);
  const [fromLastRun, setFromLastRun] = useState(false);
  useEffect(() => {
    if (seededRef.current || touched || allDimensions.length === 0) return;
    const fromNav = (preselectDims?.length ?? 0) > 0;
    const wanted = fromNav ? preselectDims : (fallbackDims ?? []);
    if (wanted.length === 0) return;
    seededRef.current = true;
    const seed = matchVisible(allDimensions, wanted);
    if (seed.size === 0) return;
    setSelectedDims(seed);
    setFromLastRun(!fromNav);
  }, [allDimensions, preselectDims, fallbackDims, touched]);
  return fromLastRun;
}

/**
 * The re-evaluate card's dimension picker, clean-scan toggle and scan
 * trigger.
 *
 * Scanning with standards available but none selected reports through
 * `onValidationFail` instead of starting. A one-shot clean scan is consumed
 * only once the start actually goes through, so a refused or failed start
 * leaves the toggle armed for the retry.
 *
 * With no navigation preselection the selection starts from `fallbackDims`,
 * the project's last finished run; `seededFromLastRun` says it did.
 */
export function useDimensionSelection({ allDimensions, info, branch, scopePath, onStart, onValidationFail, preselectDims = [], fallbackDims = [], project = null, timeLimitS = null }) {
  const set = useDimensionSet(allDimensions);
  const { selectedDims, setSelectedDims, refuseEmptySelection } = set;
  const [cleanScan, setCleanScan] = useState(CLEAN_PERSIST.OFF);
  // The user's own picks end every automatic seeding.
  const [touched, setTouched] = useState(false);
  const touch = (fn) => (...a) => { setTouched(true); fn(...a); };
  const toggleDim = touch(set.toggleDim);
  const selectAll = touch(set.selectAll);
  const clearAll = touch(set.clearAll);

  const fromLastRun = useSeedPreselectedDims({ allDimensions, preselectDims, fallbackDims, setSelectedDims, touched });

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

  // "as your last run" holds only while the selection is still that seed.
  return { selectedDims, toggleDim, selectAll, clearAll, handleScan, cleanScan, setCleanScan, seededFromLastRun: fromLastRun && !touched };
}
