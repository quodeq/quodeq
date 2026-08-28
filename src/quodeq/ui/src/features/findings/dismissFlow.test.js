import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  buildDismissPayload, resolveDismissTargetProject, dismissWithReconcile,
} from './dismissFlow.js';

// ── buildDismissPayload ────────────────────────────────────────────────

test('buildDismissPayload splits a file:line spec and keeps an explicit line', () => {
  const p = buildDismissPayload({ file: 'src/a.py:12', principle: 'P', severity: 'major', reason: 'r' });
  assert.equal(p.file, 'src/a.py');
  assert.equal(p.line, 12);

  const explicit = buildDismissPayload({ file: 'src/a.py:12', line: 7, principle: 'P', reason: 'r' });
  assert.equal(explicit.line, 7);
});

test('buildDismissPayload falls back req -> principle and dimension -> fallbackDimension', () => {
  const p = buildDismissPayload({ file: 'a.py', principle: 'Input Validation', reason: 'r' }, 'Security');
  assert.equal(p.req, 'Input Validation');
  assert.equal(p.dimension, 'Security');

  const own = buildDismissPayload({ file: 'a.py', req: 'REQ-1', dimension: 'Testing', principle: 'P', reason: 'r' }, 'Security');
  assert.equal(own.req, 'REQ-1');
  assert.equal(own.dimension, 'Testing');
});

test('buildDismissPayload defaults every optional field to its empty shape', () => {
  const p = buildDismissPayload({ file: 'a.py', principle: 'P', reason: 'r' });
  assert.deepEqual(
    { title: p.title, reqRefs: p.reqRefs, context: p.context, snippet: p.snippet, scope: p.scope, endLine: p.endLine, line: p.line },
    { title: '', reqRefs: [], context: '', snippet: '', scope: '', endLine: 0, line: 0 },
  );
});

// ── resolveDismissTargetProject ────────────────────────────────────────
// The recurring identity-divergence class: a cross-project entry must
// dismiss into the project the finding belongs to, never the selection.

test('resolveDismissTargetProject prefers the entry own project', () => {
  assert.equal(
    resolveDismissTargetProject({ explicitProject: 'other-proj', selectedProject: 'proj1' }),
    'other-proj',
  );
});

test('resolveDismissTargetProject falls back to the selected project', () => {
  assert.equal(
    resolveDismissTargetProject({ explicitProject: undefined, selectedProject: 'proj1' }),
    'proj1',
  );
  assert.equal(
    resolveDismissTargetProject({ explicitProject: '', selectedProject: 'proj1' }),
    'proj1',
  );
});

// ── dismissWithReconcile ───────────────────────────────────────────────

function makeDeps(result = { scores: { dimensions: [] }, delta: { d: 1 } }) {
  const calls = { dismiss: [], applyDelta: [], reconcile: 0, bump: 0 };
  return {
    calls,
    result,
    deps: {
      dismissFinding: async (project, payload) => { calls.dismiss.push([project, payload]); return result; },
      applyDelta: (project, scores, delta) => calls.applyDelta.push([project, scores, delta]),
      scheduleDashboardReconcile: () => { calls.reconcile += 1; },
      bumpDismissRefresh: () => { calls.bump += 1; },
    },
  };
}

test('dismissWithReconcile posts into the resolved project with run_id and runs the full tail once', async () => {
  const { calls, deps, result } = makeDeps();
  const out = await dismissWithReconcile({
    violation: { file: 'a.py', line: 1, principle: 'P', severity: 'major', reason: 'r' },
    fallbackDimension: 'Security',
    runId: 'r1',
    explicitProject: 'other-proj',
    selectedProject: 'proj1',
    deps,
  });
  assert.equal(out, result);
  assert.equal(calls.dismiss.length, 1);
  const [project, payload] = calls.dismiss[0];
  assert.equal(project, 'other-proj');
  assert.equal(payload.run_id, 'r1');
  assert.equal(payload.dimension, 'Security');
  // The delta patch targets the SAME resolved project as the POST.
  assert.deepEqual(calls.applyDelta, [['other-proj', result.scores, result.delta]]);
  assert.equal(calls.reconcile, 1);
  assert.equal(calls.bump, 1);
});

test('dismissWithReconcile falls back to the selected project when the entry carries none', async () => {
  const { calls, deps } = makeDeps();
  await dismissWithReconcile({
    violation: { file: 'a.py', principle: 'P', reason: 'r' },
    runId: 'r1',
    selectedProject: 'proj1',
    deps,
  });
  assert.equal(calls.dismiss[0][0], 'proj1');
  assert.equal(calls.applyDelta[0][0], 'proj1');
});

test('dismissWithReconcile tolerates absent optional tail callbacks', async () => {
  let posted = null;
  const out = await dismissWithReconcile({
    violation: { file: 'a.py', principle: 'P', reason: 'r' },
    selectedProject: 'proj1',
    deps: { dismissFinding: async (project, payload) => { posted = [project, payload]; return { ok: true }; } },
  });
  assert.deepEqual(out, { ok: true });
  assert.equal(posted[0], 'proj1');
});

test('dismissWithReconcile skips the tail entirely when the POST rejects', async () => {
  const { calls, deps } = makeDeps();
  deps.dismissFinding = async () => { throw new Error('boom'); };
  await assert.rejects(
    dismissWithReconcile({
      violation: { file: 'a.py', principle: 'P', reason: 'r' },
      selectedProject: 'proj1',
      deps,
    }),
    /boom/,
  );
  assert.equal(calls.applyDelta.length, 0);
  assert.equal(calls.reconcile, 0);
  assert.equal(calls.bump, 0);
});
