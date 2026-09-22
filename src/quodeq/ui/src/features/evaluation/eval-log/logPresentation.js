// Job/stream lifecycle presentation shared between useJobLogStream (decides
// WHEN a run reached a terminal state) and EvalLogProvider (decides WHAT
// WORD/LINE to show for it -- the side-pane window title and the log body's
// closing line).
import { t } from '../../../strings/index.js';

// Terminal-state text, resolved once at module scope. Safe per
// strings/moduleScope.test.js's documented convention: en.json is a static
// import fully evaluated before this module's body runs, and this file
// introduces no cycle back into strings/index.js.
export const TERMINAL_STATE_LINE = {
  cancelled: t('evaluate.logCancelled'),
  failed: t('evaluate.logFailed'),
  lost: t('evaluate.logLost'),
  done: t('evaluate.logComplete'),
  complete: t('evaluate.logComplete'),
  completed: t('evaluate.logComplete'),
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
  running: 'running',
  done: 'completed',
  failed: 'failed',
  cancelled: 'cancelled',
  lost: 'lost',
};
