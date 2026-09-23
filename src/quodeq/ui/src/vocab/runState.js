// Mirror of src/quodeq/core/run/state.py:RunState. The wire values of
// status.json, the evaluations index and every API `status`/`state` field.
export const RUN_STATE = Object.freeze({
  PENDING: 'pending',
  RUNNING: 'running',
  FINALIZING: 'finalizing',
  DONE: 'done',
  FAILED: 'failed',
  CANCELLED: 'cancelled',
});
export const TERMINAL_RUN_STATES = Object.freeze(new Set([RUN_STATE.DONE, RUN_STATE.FAILED, RUN_STATE.CANCELLED]));
