// Backend API failures -> translated copy.
//
// The error envelope is {error, code}. `error` is the backend's English
// sentence: useful in a console or a bug report, but it is written in Python
// source and can never be translated from the UI. `code` is the only part
// that a catalog can key on, and the shared request() helper used to drop it
// on the floor -- so every screen fell back to showing raw English.
//
// WHICH CODES ARE MAPPED, AND WHY NOT ALL OF THEM
//
// A code is only mapped when the code itself is as informative as the
// message it replaces. That rules out the coarse ones: NOT_FOUND is emitted
// at 32 sites covering "Project not found", "Run not found", "Eval file not
// found", "Violation data not found", "Dashboard data not found" and more.
// Mapping it would trade a specific English sentence for a vague translated
// one, which is a worse product, not a more international one. Several tests
// assert that specific message reaches the user verbatim, and they are right
// to.
//
// So the remaining English is bounded and named rather than hidden: it is
// exactly the set of coarse codes. Sharpening those backend-side (a distinct
// code per condition, and one naming convention -- the API currently emits
// both NOT_FOUND and not_found for the same thing) is what unblocks the
// rest, and it is an API change, not a UI one.
import { t } from './index.js';

const CODE_KEYS = {
  // Clone / repository registration. This copy previously lived as a
  // hardcoded English switch in RepoScanStep; it moved here unchanged.
  AUTH_REQUIRED: 'apiError.cloneAuthRequired',
  NETWORK_ERROR: 'apiError.cloneNetwork',
  REPO_NOT_FOUND: 'apiError.cloneRepoNotFound',
  DEST_EXISTS: 'apiError.cloneDestExists',
  DISK_ERROR: 'apiError.cloneDiskError',
  INVALID_REPO_URL: 'apiError.invalidRepoUrl',
  INVALID_URL: 'apiError.invalidRepoUrl',
  INVALID_REPO: 'apiError.invalidRepoUrl',
  INVALID_CLONE_DEST: 'apiError.invalidCloneDest',
  MISSING_CLONE_DEST: 'apiError.missingCloneDest',
  MISSING_REPO: 'apiError.missingRepo',
  PROJECT_EXISTS: 'apiError.projectExists',
  FOREIGN_REPO: 'apiError.foreignRepo',
  NOT_LOCAL: 'apiError.notLocal',
  PATH_MISSING: 'apiError.pathMissing',
  MISSING_PATH: 'apiError.pathMissing',
  NOT_DIR: 'apiError.notDirectory',
  REGISTRATION_FAILED: 'apiError.registrationFailed',

  // Provider configuration.
  MISSING_API_KEY: 'apiError.missingApiKey',
  PROVIDER_UNAVAILABLE: 'apiError.providerUnavailable',
  MODEL_REQUIRED: 'apiError.modelRequired',

  // Evaluation lifecycle.
  ALREADY_FINISHED: 'apiError.alreadyFinished',
  STILL_RUNNING: 'apiError.stillRunning',

  // Standards library.
  LIBRARY_NOT_CONFIGURED: 'apiError.libraryNotConfigured',
  BAD_ZIP: 'apiError.badZip',

  // Transport conditions where the code says everything the message does.
  TOO_LARGE: 'apiError.tooLarge',
  RATE_LIMITED: 'apiError.rateLimited',
  UNAUTHORIZED: 'apiError.unauthorized',
  FORBIDDEN: 'apiError.forbidden',

  // Shared results repository: connect (PUT /api/shared/config), refresh,
  // publish (routes_shared_config.py), and the assistant's own gate for
  // starting a session against it (assistant_routes.py's _shared_source_error).
  NO_SHARED_REPO: 'apiError.noSharedRepo',
  SHARED_REPO_UNAVAILABLE: 'apiError.sharedRepoUnavailable',
  URL_REQUIRED: 'apiError.urlRequired',
  CLONE_FAILED: 'apiError.sharedRepoCloneFailed',
  UNSUPPORTED_VERSION: 'apiError.sharedRepoUnsupportedVersion',
  REFRESH_FAILED: 'apiError.sharedRepoRefreshFailed',
  PUBLISH_IN_PROGRESS: 'apiError.publishInProgress',
  PUBLISH_START_FAILED: 'apiError.publishStartFailed',

  // Assistant workspace: diff/apply/discard on the isolated write worktree
  // (assistant_workspace_routes.py).
  WORKSPACE_DIFF_FAILED: 'apiError.workspaceDiffFailed',
  TURN_IN_PROGRESS: 'apiError.turnInProgress',
  WORKSPACE_DISCARD_FAILED: 'apiError.workspaceDiscardFailed',
  WORKSPACE_APPLY_FAILED: 'apiError.workspaceApplyFailed',
  WORKSPACE_PR_FAILED: 'apiError.workspacePrFailed',

  // Scores (_scores_routes.py).
  SCORES_READ_FAILED: 'apiError.scoresReadFailed',

  // Confirmation gates: delete-all findings, delete project.
  CONFIRMATION_REQUIRED: 'apiError.confirmationRequired',
};

/** The catalog key for a backend code, or null when the code is unmapped. */
export function apiErrorKey(code) {
  if (typeof code !== 'string' || code === '') return null;
  // Case-normalized: the backend emits both NOT_FOUND and not_found for the
  // same condition (also FORBIDDEN/forbidden, CONFLICT/conflict), an accident
  // of two route generations rather than a distinction anyone intended.
  const normalized = code.toUpperCase();
  // Upper-casing already rules out an inherited hit ('constructor' becomes
  // 'CONSTRUCTOR', which Object.prototype does not have), so hasOwn is not
  // load-bearing today. It is here so the guarantee survives someone
  // relaxing the normalization later.
  return Object.hasOwn(CODE_KEYS, normalized) ? CODE_KEYS[normalized] : null;
}

/**
 * Message to show for a failed API call.
 *
 * Order: a mapped code wins, because that copy is translated. Otherwise the
 * backend's own sentence, which is English but SPECIFIC -- dropping it would
 * regress the product for every unmapped code. The caller's fallback key is
 * the last resort, for failures that carry no message at all (network drop,
 * timeout).
 *
 * @param {unknown} err        the rejected error from the api layer
 * @param {string} fallbackKey catalog key describing what the caller was doing
 */
export function apiErrorMessage(err, fallbackKey) {
  const key = apiErrorKey(err?.code);
  if (key) return t(key);
  const message = err?.message;
  return (typeof message === 'string' && message !== '') ? message : t(fallbackKey);
}
