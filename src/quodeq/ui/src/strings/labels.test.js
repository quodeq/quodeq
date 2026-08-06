// scopeGateRuleLabel is new alongside the scope_downgrade badge in
// FileDetailPage.jsx (see analysis/mcp/scope_gate.py for the two rule names
// it renders). It follows the same known-set-or-raw-fallback shape as
// severityLabel/jobStatusLabel/granularityLabel above it in labels.js.
import test from 'node:test';
import assert from 'node:assert/strict';

import { scopeGateRuleLabel } from './labels.js';

test('scopeGateRuleLabel resolves both rule names scope_gate.py can stamp', () => {
  assert.equal(scopeGateRuleLabel('sourceless_path'), 'no reachable source');
  assert.equal(scopeGateRuleLabel('cross_principal'), 'cross-principal');
});

test('scopeGateRuleLabel falls through to the raw value for an unknown rule', () => {
  // _restore now drops any scope_downgrade marker it did not itself write,
  // but this label helper renders whatever "rule" the marker carries -- an
  // unrecognized value must degrade to visible text, not a missing-key
  // placeholder like "scopeGateRule.remote_ingress".
  assert.equal(scopeGateRuleLabel('remote_ingress'), 'remote_ingress');
});
