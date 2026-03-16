/**
 * Project model — a project entry from the projects listing.
 *
 * @typedef {Object} Project
 * @property {string}       name
 * @property {string|null}  id
 * @property {string|null}  parent
 * @property {string|null}  displayName
 * @property {string|null}  discipline
 * @property {string|null}  path
 * @property {string|null}  location    - 'local' | 'online'
 * @property {boolean|null} pathExists
 * @property {string|null}  latestDate
 * @property {string|null}  latestRunId
 * @property {string|null}  latestGrade
 * @property {number|null}  latestScore
 * @property {number}       runsCount
 * @property {number|null}  filesCount
 */

/**
 * Create a canonical Project from a raw API object.
 *
 * @param {Object} raw
 * @returns {Project}
 */
export function createProject(raw) {
  if (!raw || typeof raw !== 'object') return raw;
  return {
    name:         raw.name ?? '',
    id:           raw.id ?? null,
    parent:       raw.parent ?? null,
    displayName:  raw.displayName ?? null,
    discipline:   raw.discipline ?? null,
    path:         raw.path ?? null,
    location:     raw.location ?? null,
    pathExists:   raw.pathExists ?? null,
    latestDate:   raw.latestDate ?? null,
    latestRunId:  raw.latestRunId ?? null,
    latestGrade:  raw.latestGrade ?? null,
    latestScore:  raw.latestScore ?? null,
    runsCount:    raw.runsCount ?? 0,
    filesCount:   raw.filesCount ?? null,
  };
}
