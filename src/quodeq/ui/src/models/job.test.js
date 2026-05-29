import test from 'node:test';
import assert from 'node:assert/strict';
import { createJob } from './job.js';

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
