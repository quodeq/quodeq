/**
 * Which failed connect the user has closed. The connect slot stays in ERROR
 * until the next connect is claimed, so without this a mistyped URL would
 * reopen its card on every visit. A failure is identified by the slot's
 * `finishedAt`; a later failure has a different one and shows again. Kept in
 * browser storage so the dismissal outlives a remount of the page.
 */
import { useCallback, useState } from 'react';
import { readString, writeString } from '../../../adapters/storage.js';

export const DISMISSED_CONNECT_KEY = 'quodeq-connect-failure-dismissed-at';

/**
 * @param {Object|null} failedConnect - the connect slot when it is in ERROR, else null
 * @returns {{dismissed: boolean, dismiss: () => void}} `dismissed` is true when
 *   this exact failure was closed; `dismiss` closes it.
 */
export function useDismissedConnectFailure(failedConnect) {
  const [dismissedAt, setDismissedAt] = useState(() => readString(DISMISSED_CONNECT_KEY));
  const finishedAt = failedConnect ? String(failedConnect.finishedAt ?? '') : null;
  const dismiss = useCallback(() => {
    if (finishedAt === null) return;
    writeString(DISMISSED_CONNECT_KEY, finishedAt);
    setDismissedAt(finishedAt);
  }, [finishedAt]);
  return { dismissed: finishedAt !== null && finishedAt === dismissedAt, dismiss };
}
