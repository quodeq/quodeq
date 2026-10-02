// Wire vocabularies of routes_github_access.py and shared/git_errors.py.
export const ACCESS_KIND = Object.freeze({
  OK: 'ok', AUTH_REQUIRED: 'auth_required', NOT_FOUND: 'not_found', HOST_KEY: 'host_key',
  NETWORK: 'network', TIMEOUT: 'timeout', GIT_MISSING: 'git_missing', GIT_TOO_OLD: 'git_too_old', UNKNOWN: 'unknown',
});
export const SIGN_IN_KINDS = Object.freeze([ACCESS_KIND.AUTH_REQUIRED, ACCESS_KIND.NOT_FOUND]);
export const DEVICE_FLOW_STATE = Object.freeze({
  IDLE: 'idle', AWAITING_USER: 'awaiting_user', DONE: 'done', EXPIRED: 'expired', DENIED: 'denied', ERROR: 'error',
});
export const ACCOUNT_METHOD = Object.freeze({ QUODEQ: 'quodeq', GH: 'gh', NONE: 'none' });
// The hook's own phases: the backend states plus the client-side 'starting'.
export const FLOW_PHASE = Object.freeze({ ...DEVICE_FLOW_STATE, STARTING: 'starting' });
