/** Which failed connect the user has closed; see useDismissedFailure. */
import { useDismissedFailure } from './useDismissedFailure.js';

export const DISMISSED_CONNECT_KEY = 'quodeq-connect-failure-dismissed-at';

/**
 * @param {Object|null} failedConnect - the connect slot when it is in ERROR, else null
 * @returns {{dismissed: boolean, dismiss: () => void}}
 */
export function useDismissedConnectFailure(failedConnect) {
  return useDismissedFailure(failedConnect, DISMISSED_CONNECT_KEY);
}
