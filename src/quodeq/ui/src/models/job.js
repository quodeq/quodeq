/**
 * Evaluation job model — tracks status of a running or completed evaluation.
 *
 * @typedef {Object} Job
 * @property {string}        jobId
 * @property {'running'|'done'|'failed'|'cancelled'|'lost'} status
 * @property {string|null}   phase          - 'setup' | 'analyzing' | 'scoring'
 * @property {string|null}   currentDimension
 * @property {string|null}   outputProject
 * @property {string|null}   outputRunId
 * @property {string|null}   repo
 * @property {string[]|null} dimensions
 * @property {string[]}      logs
 * @property {string|null}   startedAt
 * @property {string|null}   endedAt
 * @property {string|null}   deadlineAt     - ISO-8601 wall-clock deadline for the run; null when unlimited or not yet set
 * @property {number|null}   exitCode
 * @property {string|null}   error
 * @property {string|null}   exitReason     - Why the job ended ('deadline', 'time_limit', ...); null for clean completions and plain failures
 * @property {'internal'|'external'} source  - 'internal' = launched from dashboard; 'external' = CLI/CI
 * @property {string|null}   aiProvider     - Provider this job is actually using (e.g. 'ollama', 'llamacpp')
 * @property {string|null}   aiModel        - Model this job is actually using
 */

import { fromFieldSpec } from './fieldSpec.js';

/**
 * Field table for {@link createJob}: output key -> [raw spelling(s), default].
 */
const JOB_FIELDS = {
  jobId:            ['jobId', ''],
  status:           ['status', 'running'],
  phase:            ['phase', null],
  currentDimension: ['currentDimension', null],
  outputProject:    ['outputProject', null],
  outputRunId:      ['outputRunId', null],
  repo:             ['repo', null],
  dimensions:       ['dimensions', null],
  logs:             ['logs', () => []],
  startedAt:        ['startedAt', null],
  endedAt:          ['endedAt', null],
  deadlineAt:       ['deadlineAt', null],
  exitCode:         ['exitCode', null],
  error:            ['error', null],
  exitReason:       ['exitReason', null],
  source:           ['source', 'internal'],
  aiProvider:       ['aiProvider', null],
  aiModel:          ['aiModel', null],
};

/**
 * Create a canonical Job from a raw API object.
 *
 * @param {Object} raw
 * @returns {Job}
 */
export function createJob(raw) {
  if (!raw || typeof raw !== 'object') return raw;
  return {
    ...fromFieldSpec(raw, JOB_FIELDS),
    // Not a `??` default: anything non-numeric (including a string seconds
    // count) is dropped rather than carried through.
    timeLimitS: typeof raw.timeLimitS === 'number' ? raw.timeLimitS : null,
  };
}
