import test from 'node:test';
import assert from 'node:assert/strict';
import { apiErrorKey, apiErrorMessage } from './apiErrors.js';
import catalog from './en.json' with { type: 'json' };

test('every mapped code resolves to a key that exists in the catalog', () => {
  // A missing key renders as the key itself, and the jsx-no-literals ratchet
  // structurally cannot see that -- so it has to be asserted.
  for (const code of ['AUTH_REQUIRED', 'DEST_EXISTS', 'MODEL_REQUIRED', 'BAD_ZIP', 'TOO_LARGE']) {
    const key = apiErrorKey(code);
    assert.ok(key, `${code} should be mapped`);
    assert.ok(key in catalog, `${key} missing from en.json`);
  }
});

test('lookup is case-insensitive, because the backend emits both conventions', () => {
  assert.equal(apiErrorKey('forbidden'), apiErrorKey('FORBIDDEN'));
  assert.ok(apiErrorKey('forbidden'));
});

test('unmapped and malformed codes resolve to null', () => {
  // NOT_FOUND is deliberately unmapped: it covers seven distinct backend
  // messages, so mapping it would replace a specific sentence with a vague one.
  for (const code of ['NOT_FOUND', 'INVALID_INPUT', 'INTERNAL_ERROR', 'WAT', '', null, undefined, 42]) {
    assert.equal(apiErrorKey(code), null, `${String(code)} should not be mapped`);
  }
});

test('inherited property names never resolve to a key', () => {
  for (const name of ['constructor', 'toString', 'valueOf', 'hasOwnProperty']) {
    assert.equal(apiErrorKey(name), null);
    assert.equal(apiErrorKey(name.toUpperCase()), null);
  }
});

test('a mapped code wins over the backend message, and is translated', () => {
  const msg = apiErrorMessage({ code: 'REPO_NOT_FOUND', message: 'repo missing' }, 'x.y');
  assert.equal(msg, catalog['apiError.cloneRepoNotFound']);
  assert.notEqual(msg, 'repo missing');
});

// The 13 Group D codes (D1-D4): error_response(message, status, code) calls
// added across assistant_routes.py, assistant_workspace_routes.py,
// routes_shared_config.py and _scores_routes.py, but never mapped here until
// now -- so every one of them fell through to the raw backend sentence. Each
// assertion proves the code now resolves to its own translated key instead.
test('every Group D code maps to a translated key distinct from its raw backend message', () => {
  const cases = [
    ['NO_SHARED_REPO', 'no shared repository configured', 'apiError.noSharedRepo'],
    ['SHARED_REPO_UNAVAILABLE', 'shared repository unavailable: missing', 'apiError.sharedRepoUnavailable'],
    ['WORKSPACE_DIFF_FAILED', 'diff failed', 'apiError.workspaceDiffFailed'],
    ['TURN_IN_PROGRESS', 'a turn or workspace action is in progress; wait for it to finish', 'apiError.turnInProgress'],
    ['WORKSPACE_DISCARD_FAILED', 'discard failed', 'apiError.workspaceDiscardFailed'],
    ['URL_REQUIRED', 'url is required', 'apiError.urlRequired'],
    ['CLONE_FAILED', 'could not clone the repository, check that git can access <url>', 'apiError.sharedRepoCloneFailed'],
    ['UNSUPPORTED_VERSION', 'this shared repository requires a newer version of quodeq', 'apiError.sharedRepoUnsupportedVersion'],
    ['REFRESH_FAILED', 'some refresh failure reason', 'apiError.sharedRepoRefreshFailed'],
    ['PUBLISH_IN_PROGRESS', 'a publish is already running', 'apiError.publishInProgress'],
    ['PUBLISH_START_FAILED', 'could not start the publish job, see server logs', 'apiError.publishStartFailed'],
    ['SCORES_READ_FAILED', 'could not read run scores', 'apiError.scoresReadFailed'],
    ['CONFIRMATION_REQUIRED', 'Use ?confirm=true to confirm deletion', 'apiError.confirmationRequired'],
  ];
  for (const [code, rawMessage, expectedKey] of cases) {
    const key = apiErrorKey(code);
    assert.equal(key, expectedKey, `${code} should map to ${expectedKey}`);
    assert.ok(key in catalog, `${key} missing from en.json`);
    const msg = apiErrorMessage({ code, message: rawMessage }, 'x.y');
    assert.equal(msg, catalog[expectedKey], `${code} should render its mapped copy`);
    assert.notEqual(msg, rawMessage, `${code} must not fall through to the raw backend message`);
  }
});

// The specificity trade-off, pinned: an unmapped code must keep showing the
// backend's own sentence. Several screens have tests asserting that message
// reaches the user verbatim, and dropping it to a vague translated string
// would regress the product for every code that is not yet mapped.
test('an unmapped code keeps the backend message rather than a vague fallback', () => {
  assert.equal(
    apiErrorMessage({ code: 'NOT_FOUND', message: 'Run not found' }, 'standards.deleteFailed'),
    'Run not found',
  );
});

test('the fallback key is used only when there is no message at all', () => {
  assert.equal(apiErrorMessage({ code: 'NOT_FOUND' }, 'standards.deleteFailed'), catalog['standards.deleteFailed']);
  assert.equal(apiErrorMessage({ message: '' }, 'standards.deleteFailed'), catalog['standards.deleteFailed']);
  assert.equal(apiErrorMessage(null, 'standards.deleteFailed'), catalog['standards.deleteFailed']);
  assert.equal(apiErrorMessage(undefined, 'standards.deleteFailed'), catalog['standards.deleteFailed']);
});
