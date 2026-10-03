/**
 * Scan-mode identity values for the evaluation feature. Wire/DOM strings,
 * never display text.
 *
 * SCAN_MODE ids are the ScanModeCards radio values, what
 * jobStatCells/derivations.js's deriveScanMode returns, and what
 * jobStatCells/cellBuilders.js and ScanProgressParts.jsx compare against.
 * CLEAN_PERSIST is the tri-state `value` contract ScanModeCards shares with
 * its state owner (useDimensionSelection) and with the payload builder
 * (buildScanPayload) and read-only views that derive "is clean" from it
 * (ReEvaluateCard, ReEvaluateCardParts).
 */
export const SCAN_MODE = Object.freeze({ INCREMENTAL: 'incremental', CLEAN: 'clean' });
export const CLEAN_PERSIST = Object.freeze({ OFF: 'off', ONCE: 'once', PERMANENT: 'permanent' });
