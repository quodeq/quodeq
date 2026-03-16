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
 * @property {number|null}   exitCode
 * @property {string|null}   error
 */

/**
 * Create a canonical Job from a raw API object.
 *
 * @param {Object} raw
 * @returns {Job}
 */
export function createJob(raw) {
  if (!raw || typeof raw !== 'object') return raw;
  return {
    jobId:            raw.jobId ?? '',
    status:           raw.status ?? 'running',
    phase:            raw.phase ?? null,
    currentDimension: raw.currentDimension ?? null,
    outputProject:    raw.outputProject ?? null,
    outputRunId:      raw.outputRunId ?? null,
    repo:             raw.repo ?? null,
    dimensions:       raw.dimensions ?? null,
    logs:             raw.logs ?? [],
    startedAt:        raw.startedAt ?? null,
    endedAt:          raw.endedAt ?? null,
    exitCode:         raw.exitCode ?? null,
    error:            raw.error ?? null,
  };
}
