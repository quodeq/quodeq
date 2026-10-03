/**
 * Which failed job slot the user has closed. A slot stays in ERROR until the
 * next job is claimed, so without this a failure would reopen its card on
 * every visit. A failure is identified by the slot's `finishedAt`; a later
 * failure has a different one and shows again. Kept in browser storage so the
 * dismissal outlives a remount of the page.
 */
import { useCallback, useState } from 'react';
import { readString, writeString } from '../../../adapters/storage.js';

/**
 * @param {Object|null} failedSlot - the slot when it is in ERROR, else null
 * @param {string} storageKey - where this job's dismissal is remembered
 * @returns {{dismissed: boolean, dismiss: () => void}} `dismissed` is true when
 *   this exact failure was closed; `dismiss` closes it.
 */
export function useDismissedFailure(failedSlot, storageKey) {
  const [dismissedAt, setDismissedAt] = useState(() => readString(storageKey));
  const finishedAt = failedSlot ? String(failedSlot.finishedAt ?? '') : null;
  const dismiss = useCallback(() => {
    if (finishedAt === null) return;
    writeString(storageKey, finishedAt);
    setDismissedAt(finishedAt);
  }, [finishedAt, storageKey]);
  return { dismissed: finishedAt !== null && finishedAt === dismissedAt, dismiss };
}
