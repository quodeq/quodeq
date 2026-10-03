/**
 * Small helpers the Settings screen's tabs and sections share.
 */

/**
 * Wrap a local provider's concurrency probe so a failure is logged under the
 * provider's name before it reaches the tab's error message.
 * @param {() => Promise<Object>} probe
 * @param {string} providerLabel Provider name as it appears in the log line.
 * @returns {() => Promise<Object>}
 */
export function warnAndRethrow(probe, providerLabel) {
  return () => probe().catch((err) => {
    console.warn(`${providerLabel} concurrency test failed`, err);
    throw err;
  });
}

/**
 * Run `task` unless a previous run still holds `inFlightRef`, so a
 * double-clicked mutation only fires once. A failure goes to `onError` and is
 * rethrown; the ref is released either way.
 * @param {{current: boolean}} inFlightRef
 * @param {() => Promise<*>} task
 * @param {(err: Error) => void} onError
 * @returns {Promise<*>} The task's result, or undefined when skipped.
 */
export async function runExclusive(inFlightRef, task, onError) {
  if (inFlightRef.current) return undefined;
  inFlightRef.current = true;
  try {
    return await task();
  } catch (err) {
    onError(err);
    throw err;
  } finally {
    inFlightRef.current = false;
  }
}

/**
 * Open a provider's log window, or close it when it is already open.
 * @param {{open: boolean, openLog: () => void, closeLog: () => void}} log
 */
export function toggleLogWindow(log) {
  return log.open ? log.closeLog() : log.openLog();
}
