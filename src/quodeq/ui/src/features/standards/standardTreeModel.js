/**
 * Pure tree-mutation builders for the standards editor. Each returns
 * {standard, selectedNode}: the new (deep-cloned) standard plus the node the
 * caller should select next. The hook composes these with its React state —
 * NOT purity-fixed here: `setSelectedNode` still gets called from INSIDE the
 * `setStandard` updater at the call site (useStandardDetail.js), a
 * pre-existing StrictMode double-invoke hazard this move deliberately leaves
 * in place (see the hook for the flagged follow-up).
 */
import { generateRequirementId } from './utils.js';
import { deepClone } from '../../utils/deepClone.js';

export function addPrincipleToStandard(standard) {
  const next = deepClone(standard);
  next.principles.push({ name: '', description: '', requirements: [] });
  return { standard: next, selectedNode: { type: 'principle', index: next.principles.length - 1 } };
}

export function removePrincipleFromStandard(standard, index) {
  const next = deepClone(standard);
  next.principles.splice(index, 1);
  return { standard: next, selectedNode: { type: 'root' } };
}

export function addRequirementToStandard(standard, principleIndex) {
  const next = deepClone(standard);
  const principle = next.principles[principleIndex];
  // Absent principle (stale/out-of-range index): skip the mutation and land
  // the selection back at root rather than indexing into undefined.
  if (!principle) return { standard: next, selectedNode: { type: 'root' } };
  // The principle itself may exist without a requirements array yet
  // (e.g. hand-edited/imported data); default it before pushing.
  principle.requirements ??= [];
  const seq = principle.requirements.length + 1;
  const autoId = generateRequirementId(next.id, principle.name, seq);
  principle.requirements.push({ id: autoId, text: '', description: '', refs: [] });
  return {
    standard: next,
    selectedNode: { type: 'requirement', principleIndex, reqIndex: principle.requirements.length - 1 },
  };
}

export function removeRequirementFromStandard(standard, principleIndex, reqIndex) {
  const next = deepClone(standard);
  const principle = next.principles[principleIndex];
  // Absent principle: nothing to remove from, skip the splice. A present
  // principle may still lack a requirements array; default it first.
  if (principle) {
    principle.requirements ??= [];
    principle.requirements.splice(reqIndex, 1);
  }
  return { standard: next, selectedNode: { type: 'principle', index: principleIndex } };
}

/** Set a nested field by path (e.g. ['principles', 0, 'name']). No selection change. */
export function updateStandardField(standard, path, value) {
  const next = deepClone(standard);
  let target = next;
  for (let i = 0; i < path.length - 1; i += 1) target = target[path[i]];
  target[path[path.length - 1]] = value;
  return next;
}
