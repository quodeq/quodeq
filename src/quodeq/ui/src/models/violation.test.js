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
