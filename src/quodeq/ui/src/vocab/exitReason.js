// Mirror of src/quodeq/core/run/exit_reason.py:ExitReason (run and dimension exit reasons).
export const EXIT_REASON = Object.freeze({
  DONE: 'done', TIME_LIMIT: 'time_limit', DEADLINE: 'deadline', FAILURE_STREAK: 'failure_streak',
  CANCELLED: 'cancelled', ERROR: 'error', STALE_DETECTED: 'stale_detected',
  STALE_LEGACY_PID_DEAD: 'stale_legacy_pid_dead', STALE_LEGACY_NO_PID: 'stale_legacy_no_pid',
});
