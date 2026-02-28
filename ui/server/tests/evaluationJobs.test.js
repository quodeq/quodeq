import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { createJobManager } from '../src/jobs/evaluationJobs.js';

function createFakeSpawn({ exitCode = 0, stdoutChunks = [], stderrChunks = [] } = {}) {
  return () => {
    const child = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();

    queueMicrotask(() => {
      stdoutChunks.forEach((chunk) => child.stdout.emit('data', chunk));
      stderrChunks.forEach((chunk) => child.stderr.emit('data', chunk));
      child.emit('close', exitCode);
    });

    return child;
  };
}

test('startJob requires repo input', () => {
  const manager = createJobManager({
    repoRoot: process.cwd(),
    evaluateCommand: ['uv', 'run', 'codecompass', 'evaluate'],
    spawnImpl: createFakeSpawn()
  });

  assert.throws(() => manager.startJob({}), /Repository is required/);
});

test('startJob runs and collects logs until completion', async () => {
  const manager = createJobManager({
    repoRoot: process.cwd(),
    evaluateCommand: ['uv', 'run', 'codecompass', 'evaluate'],
    spawnImpl: createFakeSpawn({
      stdoutChunks: ['Report path: /app/reports/sample-project/20260220/evaluation\n', 'done\n'],
      exitCode: 0
    })
  });

  const started = manager.startJob({ repo: 'git@github.com:org/repo.git', dimensions: 'mnt' });
  assert.equal(started.status, 'running');

  await new Promise((resolve) => setTimeout(resolve, 10));

  const finished = manager.getJob(started.jobId);
  assert.equal(finished.status, 'completed');
  assert.equal(finished.outputProject, 'sample-project');
  assert.equal(finished.outputRunId, '20260220');
  assert.ok(finished.logs.length >= 2);
});
