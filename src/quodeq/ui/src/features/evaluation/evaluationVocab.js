// The eval-log SSE connection lifecycle: written by eval-log/useJobLogStream.js,
// read by eval-log/EvalLogProvider.jsx. 'done' means "the stream closed", not
// JOB_STATUS.DONE (though the two coincide on a clean finish).
export const LOG_STREAM_STATUS = Object.freeze({
  IDLE: 'idle', STREAMING: 'streaming', DONE: 'done', ERROR: 'error',
});
