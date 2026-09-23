// scopeGateRuleLabel renders the rule a finding's scopeDowngrade marker names
// (analysis/mcp/scope_gate_rules.py, mirrored in vocab/scopeGateRule.js). It
// follows the same known-set-or-raw-fallback shape as the other helpers in
// labels.js.
import test from 'node:test';
import assert from 'node:assert/strict';

import { scopeGateRuleLabel } from './labels.js';

test('scopeGateRuleLabel resolves every rule name the scope gate can stamp', () => {
  assert.equal(scopeGateRuleLabel('sourceless_path'), 'no reachable source');
  assert.equal(scopeGateRuleLabel('cross_principal'), 'cross-principal');
  assert.equal(scopeGateRuleLabel('single_host_topology'), 'single-host deployment');
  assert.equal(scopeGateRuleLabel('loopback_transport'), 'loopback-only transport');
});

test('scopeGateRuleLabel falls through to the raw value for an unknown rule', () => {
  // _restore now drops any scope_downgrade marker it did not itself write,
  // but this label helper renders whatever "rule" the marker carries -- an
  // unrecognized value must degrade to visible text, not a missing-key
  // placeholder like "scopeGateRule.remote_ingress".
  assert.equal(scopeGateRuleLabel('remote_ingress'), 'remote_ingress');
});
