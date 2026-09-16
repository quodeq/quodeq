/**
 * Scan-mode identity values shared by the evaluation form's mode cards, the
 * clean-scan toggle and the live stat strip. Wire/DOM strings, never display
 * text: SCAN_MODE ids are the radio values and what deriveScanMode returns;
 * CLEAN_PERSIST is the tri-state `value` contract ScanModeCards and
 * CleanScanToggle share with buildScanPayload and useDimensionSelection.
 */
export const SCAN_MODE = Object.freeze({ INCREMENTAL: 'incremental', CLEAN: 'clean' });
export const CLEAN_PERSIST = Object.freeze({ OFF: 'off', ONCE: 'once', PERMANENT: 'permanent' });
