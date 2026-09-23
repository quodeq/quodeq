// Job/stream lifecycle presentation shared between useJobLogStream (decides
// WHEN a run reached a terminal state) and EvalLogProvider (decides WHAT
// WORD/LINE to show for it -- the side-pane window title and the log body's
// closing line).
import { t } from '../../../strings/index.js';
import { JOB_STATUS } from '../../../vocab/jobStatus.js';

// Terminal-state text, resolved once at module scope. Safe per
// strings/moduleScope.test.js's documented convention: en.json is a static
// import fully evaluated before this module's body runs, and this file
// introduces no cycle back into strings/index.js.
//
// No 'complete'/'completed' keys: the server's SSE done-frame (and the
// in-memory/status.json fallbacks in _log_tail_helpers._stream_terminal_state)
// only ever sends a JOB_STATUS or RUN_STATE value, and both spell the done
// state 'done'. Those legacy keys were dead.
export const TERMINAL_STATE_LINE = {
  [JOB_STATUS.CANCELLED]: t('evaluate.logCancelled'),
  [JOB_STATUS.FAILED]: t('evaluate.logFailed'),
  [JOB_STATUS.LOST]: t('evaluate.logLost'),
  [JOB_STATUS.DONE]: t('evaluate.logComplete'),
};

/** The stream's `done` payload is arbitrary text, so look up own keys only:
 *  TERMINAL_STATE_LINE['constructor'] is a function, and appending that to
 *  the log would put a non-renderable value into the list. */
export function terminalLine(state) {
  return Object.hasOwn(TERMINAL_STATE_LINE, state)
    ? TERMINAL_STATE_LINE[state]
    : t('evaluate.logComplete');
}

// Side-pane window-title vocabulary. See EvalLogProvider's statusWord().
export const JOB_STATUS_WORD = {
  [JOB_STATUS.RUNNING]: 'running',
  [JOB_STATUS.DONE]: 'completed',
  [JOB_STATUS.FAILED]: 'failed',
  [JOB_STATUS.CANCELLED]: 'cancelled',
  [JOB_STATUS.LOST]: 'lost',
};
