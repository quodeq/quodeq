/**
 * Evaluation job model — tracks status of a running or completed evaluation.
 *
 * @typedef {Object} Job
 * @property {string}        jobId
 * @property {string}        status - one of JOB_STATUS's values (see vocab/jobStatus.js)
 * @property {string|null}   phase          - 'setup' | 'analyzing' | 'scoring'
 * @property {string|null}   currentDimension
 * @property {string|null}   outputProject
 * @property {string|null}   outputRunId
 * @property {string|null}   repo
 * @property {string[]|null} dimensions
 * @property {string[]}      logs
 * @property {string|null}   startedAt
 * @property {string|null}   endedAt
 * @property {string|null}   commitSha      - The commit the run evaluates; null when unknown
 * @property {string|null}   originUrl      - git origin of the run's project folder; null when unknown
 * @property {object|null}   origin         - where the run came from ({kind: 'ci'|'cli', event, workflow, pr, prUrl, runUrl}); null when not recorded
 * @property {string|null}   deadlineAt     - ISO-8601 wall-clock deadline for the run; null when unlimited or not yet set
 * @property {number|null}   exitCode
 * @property {string|null}   error
 * @property {string|null}   exitReason     - Why the job ended ('deadline', 'time_limit', ...); null for clean completions and plain failures
 * @property {'internal'|'external'} source  - 'internal' = launched from dashboard; 'external' = CLI/CI
 * @property {string|null}   aiProvider     - Provider this job is actually using (e.g. 'ollama', 'llamacpp')
 * @property {string|null}   aiModel        - Model this job is actually using
 */

import { fromFieldSpec } from './fieldSpec.js';
import { JOB_STATUS } from '../vocab/jobStatus.js';
import { RUN_STATE } from '../vocab/runState.js';

/**
 * Field table for {@link createJob}: output key -> [raw spelling(s), default].
 *
 * Two wire shapes land here. The REST job is camelCase (`to_camel_dict` of a
 * JobSnapshot). The SSE `status` frame is the raw snake_case status.json,
 * whose `state` is a RunState rather than a JobStatus. The snake_case
 * spelling comes first so that, when a frame is merged over a cached REST
 * job, the frame's fresher value wins over the stale camelCase one.
 */
const JOB_FIELDS = {
  jobId:            [['job_id', 'jobId'], ''],
  status:           [['state', 'status'], JOB_STATUS.RUNNING],
  phase:            ['phase', null],
  currentDimension: [['current_dimension', 'currentDimension'], null],
  outputProject:    ['outputProject', null],
  outputRunId:      ['outputRunId', null],
  repo:             ['repo', null],
  dimensions:       ['dimensions', null],
  logs:             ['logs', () => []],
  startedAt:        [['started_at', 'startedAt'], null],
  endedAt:          [['finalized_at', 'endedAt'], null],
  deadlineAt:       [['deadline_at', 'deadlineAt'], null],
  exitCode:         ['exitCode', null],
  error:            ['error', null],
  exitReason:       [['exit_reason', 'exitReason'], null],
  source:           ['source', 'internal'],
  aiProvider:       [['ai_provider', 'aiProvider'], null],
  aiModel:          [['ai_model', 'aiModel'], null],
  commitSha:        [['commit_sha', 'commitSha'], null],
  originUrl:        ['originUrl', null],
  origin:           ['origin', null],
};

// RunState values that have no JobStatus counterpart: the job is still going.
const RUN_STATE_IN_PROGRESS = new Set([RUN_STATE.PENDING, RUN_STATE.FINALIZING]);

/**
 * Job fields a status frame is the source of truth for. The rest of the Job
 * (outputProject, source, logs, ...) only ever arrives over REST and must be
 * kept from the cached job when a frame is applied. See {@link applyStatusFrame}.
 */
const STATUS_FRAME_FIELDS = Object.freeze([
  'jobId', 'status', 'phase', 'currentDimension', 'dimensions', 'startedAt',
  'endedAt', 'deadlineAt', 'exitReason', 'aiProvider', 'aiModel', 'timeLimitS', 'commitSha',
]);

function timeLimitOf(raw) {
  // Not a `??` default: anything non-numeric (including a string seconds
  // count) is dropped rather than carried through.
  const value = raw.time_limit_s ?? raw.timeLimitS;
  return typeof value === 'number' ? value : null;
}

/**
 * Create a canonical Job from a raw API object or a raw SSE status frame.
 *
 * @param {Object} raw
 * @returns {Job}
 */
export function createJob(raw) {
  if (!raw || typeof raw !== 'object') return raw;
  const job = fromFieldSpec(raw, JOB_FIELDS);
  if (RUN_STATE_IN_PROGRESS.has(job.status)) job.status = JOB_STATUS.RUNNING;
  return { ...job, timeLimitS: timeLimitOf(raw) };
}

/**
 * Merge a raw SSE status frame onto the cached Job (if any).
 *
 * The frame carries only what status.json knows, so REST-only fields are
 * kept from `prev`; every field the frame does know about is taken from the
 * frame, including ones it has cleared (a finished run's null
 * currentDimension must not be shadowed by the cached value).
 *
 * @param {Object|undefined} prev  cached Job, if the REST fetch already landed
 * @param {Object} frame           raw status.json payload
 * @returns {Job}
 */
export function applyStatusFrame(prev, frame) {
  const fresh = createJob(frame);
  if (!prev) return fresh;
  const next = { ...prev };
  for (const key of STATUS_FRAME_FIELDS) next[key] = fresh[key];
  return next;
}
