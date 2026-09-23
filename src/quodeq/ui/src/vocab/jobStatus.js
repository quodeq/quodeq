// Mirror of src/quodeq/core/run/job_status.py:JobStatus.
export const JOB_STATUS = Object.freeze({
  RUNNING: 'running', DONE: 'done', FAILED: 'failed', CANCELLED: 'cancelled', LOST: 'lost',
});
export const JOB_TERMINAL = Object.freeze(new Set([JOB_STATUS.DONE, JOB_STATUS.FAILED, JOB_STATUS.CANCELLED, JOB_STATUS.LOST]));
