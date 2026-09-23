// Mirror of src/quodeq/core/run/job_status.py:JobStatus.
export const JOB_STATUS = Object.freeze({
  RUNNING: 'running', DONE: 'done', FAILED: 'failed', CANCELLED: 'cancelled', LOST: 'lost',
});
export const JOB_TERMINAL = Object.freeze(new Set([JOB_STATUS.DONE, JOB_STATUS.FAILED, JOB_STATUS.CANCELLED, JOB_STATUS.LOST]));
// Excludes LOST on purpose: a lost job's subprocess may still be alive and
// writing (the tracking thread, not the process, is what was lost), so
// callers that decide "the run actually finished" must not treat LOST as
// finished. Mirrors core/run/job_status.py:JOB_FINISHED exactly.
export const JOB_FINISHED = Object.freeze(new Set([JOB_STATUS.DONE, JOB_STATUS.FAILED, JOB_STATUS.CANCELLED]));
