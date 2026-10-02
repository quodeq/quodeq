import { useEffect, useRef, useState } from 'react';
import { isSlotActive } from '../../../api/syncStatus.js';
import { apiErrorMessage } from '../../../strings/apiErrors.js';
import { useSidePane } from '../../side-pane/SidePaneContext.jsx';
import { SYNC_PHASE } from '../../../vocab/syncPhase.js';

const CODE_PROJECT_EXISTS = 'PROJECT_EXISTS'; // the pull slot's code for a local collision

// One pull run: the slot carries no run id, so a run is its project, phase and finish time.
const runKey = (slot) => (slot ? `${slot.project}|${slot.phase}|${slot.finishedAt ?? ''}` : null);

// The slot as it stood when this hook first saw it. A finished pull left over
// from an earlier visit must not paint "pulled" or a conflict on a card.
function useBaselineKey(slot) {
  const baseline = useRef(undefined);
  if (baseline.current === undefined && slot) baseline.current = runKey(slot);
  return baseline.current;
}

/**
 * Pull-to-local (shared-only cards). A pull is a background job: `shared.pull`
 * only starts it, and the outcome is read from the pull slot of the sync
 * status (`shared.pullSlot`): running, DONE (the card shows "pulled"), or
 * ERROR. A PROJECT_EXISTS error is the same-uuid/same-identity collision and
 * opens the card's inline copy confirm; any other error is toasted. The
 * projects list is refetched by useSyncStatus when the slot reaches DONE.
 */
export function usePullToLocal({ shared }) {
  const { showToast } = useSidePane();
  const slot = shared.pullSlot;
  const baseline = useBaselineKey(slot);
  const key = runKey(slot);
  const fresh = Boolean(slot) && key !== baseline;
  const [pulledIds, setPulledIds] = useState(() => new Set());
  const [dismissedKey, setDismissedKey] = useState(null);
  const reportedKey = useRef(null);

  const finished = fresh && slot.phase === SYNC_PHASE.DONE;
  const failed = fresh && slot.phase === SYNC_PHASE.ERROR;
  const collided = failed && slot.code === CODE_PROJECT_EXISTS;

  useEffect(() => {
    if (finished) setPulledIds((prev) => (prev.has(slot.project) ? prev : new Set(prev).add(slot.project)));
  }, [finished, slot?.project]);

  useEffect(() => {
    if (!failed || collided || reportedKey.current === key) return;
    reportedKey.current = key;
    showToast(apiErrorMessage({ code: slot.code, message: slot.error }, 'projects.pullFailed'));
  }, [failed, collided, key]);

  async function start(id, action) {
    setDismissedKey(key); // a started pull answers the collision; the next run has its own key
    try {
      await shared.pull(id, action);
    } catch (err) {
      showToast(apiErrorMessage(err, 'projects.pullFailed'));
    }
  }

  const conflictOpen = collided && dismissedKey !== key;
  return {
    pullConflictId: conflictOpen ? slot.project : null,
    // Same shape the import-conflict dialog reads (`kind`), plus the colliding local project.
    pullConflict: conflictOpen ? { kind: slot.conflictKind, projectId: slot.sourceProjectId } : null,
    pulledIds,
    pullingId: isSlotActive(slot) ? slot.project : null,
    handlePull: (id) => start(id),
    handleConfirmCopy: (id) => start(id, 'copy'),
    cancelConflict: () => setDismissedKey(key),
  };
}
