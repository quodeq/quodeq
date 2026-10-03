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
  // Clone / repository registration: the POST /api/projects refusal and the
  // clone job's slot error both resolve through these.
  AUTH_REQUIRED: 'apiError.cloneAuthRequired',
  NETWORK_ERROR: 'apiError.cloneNetwork',
  REPO_NOT_FOUND: 'apiError.cloneRepoNotFound',
  DEST_EXISTS: 'apiError.cloneDestExists',
  DISK_ERROR: 'apiError.cloneDiskError',
  // The clone job itself: it could not start, or one already runs.
  CLONE_START_FAILED: 'apiError.cloneStartFailed',
  CLONE_IN_PROGRESS: 'apiError.cloneInProgress',
  INVALID_REPO_URL: 'apiError.invalidRepoUrl',
  INVALID_URL: 'apiError.invalidRepoUrl',
  INVALID_REPO: 'apiError.invalidRepoUrl',
  INVALID_CLONE_DEST: 'apiError.invalidCloneDest',
  MISSING_REPO: 'apiError.missingRepo',
  PROJECT_EXISTS: 'apiError.projectExists',
  FOREIGN_REPO: 'apiError.foreignRepo',
  // A file:// evaluations repository whose folder is not a git repository.
  NOT_A_GIT_REPO: 'apiError.notAGitRepo',
  NOT_LOCAL: 'apiError.notLocal',
  PATH_MISSING: 'apiError.pathMissing',
  MISSING_PATH: 'apiError.pathMissing',
  NOT_DIR: 'apiError.notDirectory',
  // POST /api/evaluations with a git url: only the registered local copy can be evaluated.
  URL_NOT_EVALUABLE: 'apiError.urlNotEvaluable',

  // Provider configuration.
  MISSING_API_KEY: 'apiError.missingApiKey',
  PROVIDER_UNAVAILABLE: 'apiError.providerUnavailable',
  MODEL_REQUIRED: 'apiError.modelRequired',
  // POST /api/provider/key with no OS keyring and no plaintext opt-in; the
  // envelope's envVar fills the copy's {envVar}.
  KEYRING_UNAVAILABLE: 'apiError.keyringUnavailable',

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

  // Evaluations repository: connect (PUT /api/shared/config), refresh,
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
  CONNECT_IN_PROGRESS: 'apiError.connectInProgress',
  CONNECT_START_FAILED: 'apiError.connectStartFailed',
  CONNECT_FAILED: 'apiError.connectFailed',
  // The pull job's export over QUODEQ_MAX_ZIP_SIZE_MB (routes_shared_pull.py).
  PULL_TOO_LARGE: 'apiError.pullTooLarge',

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

  // Access ladder (routes_github_access.py): the pre-clone probe's verdict,
  // the clone's own new codes, and GitHub sign-in.
  ACCESS_AUTH_REQUIRED: 'apiError.accessAuthRequired',
  ACCESS_NOT_FOUND: 'apiError.accessNotFound',
  ACCESS_HOST_KEY: 'apiError.accessHostKey',
  ACCESS_NETWORK: 'apiError.accessNetwork',
  ACCESS_TIMEOUT: 'apiError.accessTimeout',
  ACCESS_GIT_MISSING: 'apiError.accessGitMissing',
  ACCESS_GIT_TOO_OLD: 'apiError.accessGitTooOld',
  ACCESS_UNKNOWN: 'apiError.accessUnknown',
  ACCESS_USE_HTTPS: 'apiError.accessUseHttps',
  CLONE_UNKNOWN: 'apiError.cloneUnknown',
  CLONE_TIMEOUT: 'apiError.cloneTimeout',
  HOST_KEY_UNVERIFIED: 'apiError.hostKeyUnverified',
  GIT_MISSING: 'apiError.gitMissing',
  TOKEN_INVALID: 'apiError.tokenInvalid',
  TOKEN_SCOPE: 'apiError.tokenScope',
  TOKEN_REQUIRED: 'apiError.tokenRequired',
  OFFLINE: 'apiError.githubOffline',
  GITHUB_NOT_CONFIGURED: 'apiError.githubNotConfigured',
  GITHUB_REFUSED: 'apiError.githubRefused',
  NO_FLOW: 'apiError.noFlow',
  FLOW_START_FAILED: 'apiError.flowStartFailed',
  FLOW_FAILED: 'apiError.flowFailed',
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

function envelopeVars(err) {
  const body = err?.body;
  return (body !== null && typeof body === 'object' && !Array.isArray(body)) ? body : undefined;
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
  // The envelope's extra fields (err.body, see api/request.js) fill any
  // {placeholder} in the mapped copy.
  if (key) return t(key, envelopeVars(err));
  const message = err?.message;
  return (typeof message === 'string' && message !== '') ? message : t(fallbackKey);
}

const ACCESS_CODE_PREFIX = 'ACCESS_';

/** The output tail the backend attached to a clone or probe failure, or ''. */
export function apiErrorDetail(err) {
  const detail = err?.body?.detail;
  return typeof detail === 'string' ? detail : '';
}

/** True for a pre-clone probe verdict (ACCESS_<KIND>), which the access panel renders. */
export function isAccessCode(code) {
  return typeof code === 'string' && code.toUpperCase().startsWith(ACCESS_CODE_PREFIX);
}
