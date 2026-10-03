/** Which failed clone the user has closed; see useDismissedFailure. */
import { useDismissedFailure } from './useDismissedFailure.js';

export const DISMISSED_CLONE_KEY = 'quodeq-clone-failure-dismissed-at';

/**
 * @param {Object|null} failedClone - the clone slot when it is in ERROR, else null
 * @returns {{dismissed: boolean, dismiss: () => void}}
 */
export function useDismissedCloneFailure(failedClone) {
  return useDismissedFailure(failedClone, DISMISSED_CLONE_KEY);
}
