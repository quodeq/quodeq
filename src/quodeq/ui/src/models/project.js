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
 * @property {string|null}  originUrl   - git remote URL the project was registered from, if any
 * @property {string|null}  location    - 'local' | 'online'
 * @property {boolean|null} pathExists
 * @property {string|null}  latestDate
 * @property {string|null}  latestRunId
 * @property {string|null}  latestDoneRunId - id of the newest run that finished (not cancelled/failed/in-progress), or null
 * @property {string|null}  latestGrade
 * @property {boolean}      summaryPending - true while the backend is still computing this project's warm-up summary
 * @property {number|null}  latestScore
 * @property {number}       runsCount
 * @property {number|null}  filesCount
 * @property {string|null}  scopePath   - subdirectory the project is scoped to, or null for the whole repo
 * @property {boolean}      hasFingerprints - true once the backend has indexed the project's files
 * @property {Object|null}  languageStats - e.g. { py: 302, js: 84 }
 * @property {string|null}  scanDate
 * @property {number|null}  totalFiles
 * @property {number|null}  analyzedFiles
 */

import { fromFieldSpec } from './fieldSpec.js';

// project.location values. ONLINE is the legacy "registered but never
// cloned" state (repository_info.json written by pre-clone registration;
// IncompleteSetupCard offers to complete it). Coincidentally spelled like
// vocab/projectSource.js's PROJECT_SOURCE.LOCAL, but a different domain:
// that one is where a project's *data* lives (this machine vs the shared
// repo), this is whether a checkout exists on disk at all.
export const PROJECT_LOCATION = Object.freeze({ LOCAL: 'local', ONLINE: 'online' });

/**
 * Field table for {@link createProject}: output key -> [raw spelling(s), default].
 */
const PROJECT_FIELDS = {
  name:            ['name', ''],
  id:              ['id', null],
  parent:          ['parent', null],
  displayName:     ['displayName', null],
  discipline:      ['discipline', null],
  path:            ['path', null],
  originUrl:       ['originUrl', null],
  location:        ['location', null],
  pathExists:      ['pathExists', null],
  latestDate:      ['latestDate', null],
  latestRunId:     ['latestRunId', null],
  latestDoneRunId: ['latestDoneRunId', null],
  latestGrade:     ['latestGrade', null],
  summaryPending:  ['summaryPending', false],
  latestScore:     ['latestScore', null],
  runsCount:       ['runsCount', 0],
  filesCount:      ['filesCount', null],
  scopePath:       ['scopePath', null],
  hasFingerprints: ['hasFingerprints', false],
  languageStats:   ['languageStats', null],
  scanDate:        ['scanDate', null],
  totalFiles:      ['totalFiles', null],
  analyzedFiles:   ['analyzedFiles', null],
};

/**
 * Create a canonical Project from a raw API object.
 *
 * @param {Object} raw
 * @returns {Project}
 */
export function createProject(raw) {
  if (!raw || typeof raw !== 'object') return raw;
  return fromFieldSpec(raw, PROJECT_FIELDS);
}
