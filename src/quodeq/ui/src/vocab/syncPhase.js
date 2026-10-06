// Mirror of src/quodeq/core/types/sync_phase.py:SyncPhase and SyncKind.
// RESOLVING and CHECKOUT are git's two phases after the download ("Resolving
// deltas", "Updating files"); a clone or connect passes through them before READING.
export const SYNC_PHASE = Object.freeze({
  CONNECTING: 'connecting', DOWNLOADING: 'downloading', RESOLVING: 'resolving', CHECKOUT: 'checkout',
  READING: 'reading', DONE: 'done', ERROR: 'error',
});
export const SYNC_KIND = Object.freeze({ CONNECT: 'connect', REFRESH: 'refresh', PULL: 'pull', CLONE: 'clone' });
// Phases in which a sync job is still working (DONE and ERROR are terminal).
export const SYNC_ACTIVE_PHASES = Object.freeze(new Set([
  SYNC_PHASE.CONNECTING, SYNC_PHASE.DOWNLOADING, SYNC_PHASE.RESOLVING, SYNC_PHASE.CHECKOUT, SYNC_PHASE.READING,
]));
