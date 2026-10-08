import test from 'node:test';
import assert from 'node:assert/strict';
import { createJob, applyStatusFrame } from './job.js';

test('createJob maps aiProvider and aiModel from API response', () => {
  const raw = { jobId: 'ext-1', aiProvider: 'llamacpp', aiModel: 'qwen3.6-27b' };
  const job = createJob(raw);
  assert.equal(job.aiProvider, 'llamacpp');
  assert.equal(job.aiModel, 'qwen3.6-27b');
});

test('createJob leaves aiProvider/aiModel null when API omits them', () => {
  const job = createJob({ jobId: 'ext-1' });
  assert.equal(job.aiProvider, null);
  assert.equal(job.aiModel, null);
});

test('createJob maps timeLimitS, including 0 (unlimited)', () => {
  assert.equal(createJob({ jobId: 'j1', timeLimitS: 600 }).timeLimitS, 600);
  assert.equal(createJob({ jobId: 'j1', timeLimitS: 0 }).timeLimitS, 0);
  assert.equal(createJob({ jobId: 'j1' }).timeLimitS, null);
});

test('createJob maps exitReason from API response', () => {
  assert.equal(createJob({ jobId: 'j1', exitReason: 'deadline' }).exitReason, 'deadline');
  assert.equal(createJob({ jobId: 'j1' }).exitReason, null);
});

test('the commit arrives from the REST job and from a status frame', () => {
  assert.equal(createJob({ jobId: 'j', commitSha: 'abc' }).commitSha, 'abc');
  assert.equal(createJob({ job_id: 'j' }).commitSha, null);
  const merged = applyStatusFrame(createJob({ jobId: 'j' }), { commit_sha: 'ed0e84b' });
  assert.equal(merged.commitSha, 'ed0e84b');
});

test('the git origin arrives from the REST job and survives a status frame', () => {
  const job = createJob({ jobId: 'j', originUrl: 'https://github.com/quodeq/quodeq' });
  assert.equal(job.originUrl, 'https://github.com/quodeq/quodeq');
  assert.equal(createJob({ jobId: 'j' }).originUrl, null);
  assert.equal(applyStatusFrame(job, { state: 'running' }).originUrl, 'https://github.com/quodeq/quodeq');
});
