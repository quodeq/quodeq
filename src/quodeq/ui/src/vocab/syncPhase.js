// Mirror of src/quodeq/core/types/sync_phase.py:SyncPhase and SyncKind.
export const SYNC_PHASE = Object.freeze({
  CONNECTING: 'connecting', DOWNLOADING: 'downloading', READING: 'reading', DONE: 'done', ERROR: 'error',
});
export const SYNC_KIND = Object.freeze({ CONNECT: 'connect', REFRESH: 'refresh', PULL: 'pull' });
// Phases in which a sync job is still working (DONE and ERROR are terminal).
export const SYNC_ACTIVE_PHASES = Object.freeze(new Set([SYNC_PHASE.CONNECTING, SYNC_PHASE.DOWNLOADING, SYNC_PHASE.READING]));
