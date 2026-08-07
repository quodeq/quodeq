// Some catalogs are built at MODULE scope -- EXIT_REASON_INFO,
// TERMINAL_STATE_LINE, CONSTELLATION_LABELS, META_COMMANDS all call t() while
// their module is initializing, not inside a render. That only works because
// en.json is a static import that is fully evaluated before any importer's
// body runs; introduce a cycle back into strings/index.js and these silently
// freeze as the key string instead of the sentence.
//
// t() returning its own key on a miss is deliberate (it keeps the UI alive),
// which is exactly why it needs asserting here: a frozen value looks like
// working code and renders as "exitReason.timeLimitLabel" in the product.
import test from 'node:test';
import assert from 'node:assert/strict';

import { EXIT_REASON_INFO, exitReasonInfo, exitReasonLabel, exitReasonHint } from '../models/exitReason.js';
import { CONSTELLATION_LABELS } from '../features/map/viz/components/galaxyViewScene.js';
import { META_COMMANDS } from '../features/assistant/commands.js';

/** A value that is still its own catalog key never got resolved. */
function assertResolved(value, label) {
  assert.equal(typeof value, 'string', `${label} should be a string`);
  assert.ok(value.length > 0, `${label} should not be empty`);
  assert.ok(
    !/^[a-z][a-zA-Z0-9]*\.[a-zA-Z0-9.]+$/.test(value),
    `${label} rendered as a raw catalog key: ${value}`,
  );
}

test('exit-reason labels and hints resolve at module init', () => {
  for (const [code, info] of Object.entries(EXIT_REASON_INFO)) {
    assertResolved(info.label, `EXIT_REASON_INFO.${code}.label`);
    if (info.hint !== null) assertResolved(info.hint, `EXIT_REASON_INFO.${code}.hint`);
  }
  assertResolved(exitReasonLabel('time_limit'), 'exitReasonLabel(time_limit)');
  assertResolved(exitReasonHint('provider_fatal'), 'exitReasonHint(provider_fatal)');
});

test('unknown exit reasons still fall through to the raw code', () => {
  assert.equal(exitReasonLabel('some_new_backend_reason'), 'some_new_backend_reason');
  assert.equal(exitReasonHint('some_new_backend_reason'), null);
});

// Inherited Object.prototype keys must not resolve to a function. This has
// to assert on exitReasonInfo itself, not on the label/hint helpers: those
// read .label/.hint off the result and coincidentally recover, while
// ScanProgress branches on `failInfo ?` and would take the "recognised
// reason" path for a truthy inherited function -- rendering an empty error
// banner and swallowing the raw failure detail underneath it.
test('inherited property names are not treated as known exit reasons', () => {
  for (const name of ['constructor', 'toString', 'valueOf', 'hasOwnProperty']) {
    assert.equal(exitReasonInfo(name), null, `exitReasonInfo(${name}) must be null`);
    assert.equal(exitReasonHint(name), null, `${name} should have no hint`);
    assert.equal(exitReasonLabel(name), name, `${name} should pass through verbatim`);
  }
});

test('constellation labels resolve at module init', () => {
  for (const [kind, label] of Object.entries(CONSTELLATION_LABELS)) {
    if (kind === '_default') continue;   // deliberately empty
    assertResolved(label, `CONSTELLATION_LABELS.${kind}`);
  }
});

test('assistant meta-command descriptions resolve at module init', () => {
  assert.ok(META_COMMANDS.length > 0);
  for (const cmd of META_COMMANDS) {
    assertResolved(cmd.description, `META_COMMANDS.${cmd.name}.description`);
  }
});
