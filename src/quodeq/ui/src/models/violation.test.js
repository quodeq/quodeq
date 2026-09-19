import test from 'node:test';
import assert from 'node:assert/strict';
import { createViolation } from './violation.js';

// Issue #656: the provenance gate's downgrade marker must survive
// canonicalization so a badge can render on affected violations. The API
// emits it camelCase (to_camel_dict); raw JSON files use snake_case.

test('createViolation maps provenanceDowngrade (camelCase from API)', () => {
  const v = createViolation({ severity: 'major', provenanceDowngrade: true });
  assert.equal(v.provenanceDowngrade, true);
});

test('createViolation maps provenance_downgrade (snake_case from raw JSON)', () => {
  const v = createViolation({ severity: 'major', provenance_downgrade: true });
  assert.equal(v.provenanceDowngrade, true);
});

test('createViolation defaults provenanceDowngrade to false when absent', () => {
  const v = createViolation({ severity: 'minor' });
  assert.equal(v.provenanceDowngrade, false);
});

test('createViolation maps carriedForward (camelCase from API)', () => {
  const v = createViolation({ severity: 'major', carriedForward: true });
  assert.equal(v.carriedForward, true);
});

test('createViolation maps carried_forward (snake_case from raw JSON)', () => {
  const v = createViolation({ severity: 'major', carried_forward: true });
  assert.equal(v.carriedForward, true);
});

test('createViolation defaults carriedForward to false when absent', () => {
  const v = createViolation({ severity: 'major' });
  assert.equal(v.carriedForward, false);
});

// The scope gate's marker is a dict naming the rule/from/to, not a bool --
// the whole point is recovering WHICH rule moved the finding, so it must
// travel as an object, not collapse to true/false like provenanceDowngrade.

test('createViolation maps scopeDowngrade (camelCase from API)', () => {
  const marker = { rule: 'sourceless_path', from: 'major', to: 'minor' };
  const v = createViolation({ severity: 'minor', scopeDowngrade: marker });
  assert.deepEqual(v.scopeDowngrade, marker);
});

test('createViolation maps scope_downgrade (snake_case from raw JSON)', () => {
  const marker = { rule: 'cross_principal', from: 'major', to: 'minor' };
  const v = createViolation({ severity: 'minor', scope_downgrade: marker });
  assert.deepEqual(v.scopeDowngrade, marker);
});

test('createViolation defaults scopeDowngrade to null when absent', () => {
  const v = createViolation({ severity: 'minor' });
  assert.equal(v.scopeDowngrade, null);
});

// The backend names a finding's principle `practiceId` on the REST paths
// (to_camel_dict) and `practice_id` on the SSE frame, which serialises the
// payload directly. A component reading `principle` sees neither unless this
// model maps both, and the live feed's rule column rendered blank because of
// the missing snake_case spelling.

test('createViolation maps practiceId (camelCase from REST)', () => {
  const v = createViolation({ severity: 'major', practiceId: 'Authenticity' });
  assert.equal(v.principle, 'Authenticity');
});

test('createViolation maps practice_id (snake_case from the SSE frame)', () => {
  const v = createViolation({ severity: 'major', practice_id: 'Authenticity' });
  assert.equal(v.principle, 'Authenticity');
});

test('createViolation still honours an explicit principle', () => {
  const v = createViolation({ severity: 'major', principle: 'Integrity' });
  assert.equal(v.principle, 'Integrity');
});

test('createViolation prefers practiceId over a legacy principle field', () => {
  const v = createViolation({ practiceId: 'Authenticity', principle: 'Integrity' });
  assert.equal(v.principle, 'Authenticity');
});

test('createViolation leaves principle null when the payload carries none', () => {
  const v = createViolation({ severity: 'minor', file: 'a.py' });
  assert.equal(v.principle, null);
});
