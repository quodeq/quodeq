// scopeGateRuleLabel renders the rule a finding's scopeDowngrade marker names
// (analysis/mcp/scope_gate_rules.py, mirrored in vocab/scopeGateRule.js). It
// follows the same known-set-or-raw-fallback shape as the other helpers in
// labels.js.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { scopeGateRuleLabel, granularityLabel, severityLabel } from './labels.js';
import { GRANULARITY } from '../utils/granularity.js';

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

test('labels.js takes its severity and granularity sets from their homes', () => {
  const src = readFileSync(new URL('./labels.js', import.meta.url), 'utf8');
  assert.doesNotMatch(src, /'critical', 'major', 'minor'/);
  assert.doesNotMatch(src, /'day', 'week', 'month'/);
  assert.deepEqual(GRANULARITY, { DAY: 'day', WEEK: 'week', MONTH: 'month' });
  assert.equal(Object.isFrozen(GRANULARITY), true);
});

test('severity and granularity labels still resolve known values and pass unknown ones through', () => {
  assert.notEqual(severityLabel('unknown'), 'severity.unknown');
  assert.notEqual(granularityLabel('week'), 'granularity.week');
  assert.equal(granularityLabel('fortnight'), 'fortnight');
});
