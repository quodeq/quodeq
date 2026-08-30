import test from 'node:test';
import assert from 'node:assert/strict';
import {
  addPrincipleToStandard, removePrincipleFromStandard,
  addRequirementToStandard, removeRequirementFromStandard, updateStandardField,
} from './standardTreeModel.js';

function makeStandard() {
  return {
    id: 'my-standard',
    name: 'My Standard',
    principles: [
      { name: 'Error Handling', description: '', requirements: [{ id: 'MYST-ERR-01', text: 'x', refs: [] }] },
      { name: 'Testing', description: '', requirements: [] },
    ],
  };
}

// ---------------------------------------------------------------------------
// addPrincipleToStandard
// ---------------------------------------------------------------------------

test('addPrincipleToStandard: appends an empty principle and selects it', () => {
  const original = makeStandard();
  const { standard, selectedNode } = addPrincipleToStandard(original);
  assert.equal(standard.principles.length, 3);
  assert.deepEqual(standard.principles[2], { name: '', description: '', requirements: [] });
  assert.deepEqual(selectedNode, { type: 'principle', index: 2 });
  // Does not mutate the input.
  assert.equal(original.principles.length, 2);
});

// ---------------------------------------------------------------------------
// removePrincipleFromStandard
// ---------------------------------------------------------------------------

test('removePrincipleFromStandard: removes the principle at index and selects root', () => {
  const original = makeStandard();
  const { standard, selectedNode } = removePrincipleFromStandard(original, 0);
  assert.equal(standard.principles.length, 1);
  assert.equal(standard.principles[0].name, 'Testing');
  assert.deepEqual(selectedNode, { type: 'root' });
  assert.equal(original.principles.length, 2); // input untouched
});

// ---------------------------------------------------------------------------
// addRequirementToStandard
// ---------------------------------------------------------------------------

test('addRequirementToStandard: sequence continues from existing requirement count', () => {
  const original = makeStandard();
  const { standard, selectedNode } = addRequirementToStandard(original, 0);
  const reqs = standard.principles[0].requirements;
  assert.equal(reqs.length, 2);
  // (requirements.length || 0) + 1 counted BEFORE the push: 1 existing -> seq 2.
  assert.equal(reqs[1].id, 'MYST-ERR-02');
  assert.deepEqual(reqs[1], { id: 'MYST-ERR-02', text: '', description: '', refs: [] });
  assert.deepEqual(selectedNode, { type: 'requirement', principleIndex: 0, reqIndex: 1 });
});

test('addRequirementToStandard: first requirement in an empty principle gets sequence 1', () => {
  const original = makeStandard();
  const { standard, selectedNode } = addRequirementToStandard(original, 1); // 'Testing', empty
  const reqs = standard.principles[1].requirements;
  assert.equal(reqs.length, 1);
  assert.equal(reqs[0].id, 'MYST-TES-01');
  assert.deepEqual(selectedNode, { type: 'requirement', principleIndex: 1, reqIndex: 0 });
});

// ---------------------------------------------------------------------------
// removeRequirementFromStandard
// ---------------------------------------------------------------------------

test('removeRequirementFromStandard: removes the requirement and selects the parent principle', () => {
  const original = makeStandard();
  const { standard, selectedNode } = removeRequirementFromStandard(original, 0, 0);
  assert.equal(standard.principles[0].requirements.length, 0);
  assert.deepEqual(selectedNode, { type: 'principle', index: 0 });
});

// ---------------------------------------------------------------------------
// updateStandardField
// ---------------------------------------------------------------------------

test('updateStandardField: sets a top-level field without mutating the input', () => {
  const original = makeStandard();
  const next = updateStandardField(original, ['name'], 'Renamed');
  assert.equal(next.name, 'Renamed');
  assert.equal(original.name, 'My Standard');
});

test('updateStandardField: walks a nested path to set a deep field', () => {
  const original = makeStandard();
  const next = updateStandardField(original, ['principles', 0, 'requirements', 0, 'text'], 'updated text');
  assert.equal(next.principles[0].requirements[0].text, 'updated text');
  assert.equal(original.principles[0].requirements[0].text, 'x');
});
