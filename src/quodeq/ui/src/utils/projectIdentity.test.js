import test from 'node:test';
import assert from 'node:assert/strict';
import { projectId, projectIdOrSelf } from './projectIdentity.js';

test('projectId prefers the id and falls back to the name', () => {
  assert.equal(projectId({ id: 'abc', name: 'repo' }), 'abc');
  assert.equal(projectId({ id: null, name: 'repo' }), 'repo');
  assert.equal(projectId({ id: '', name: '' }), '');
  assert.equal(projectId('bare-name'), undefined);
});

test('projectIdOrSelf also accepts a bare project name', () => {
  assert.equal(projectIdOrSelf({ id: 'abc', name: 'repo' }), 'abc');
  assert.equal(projectIdOrSelf({ id: null, name: 'repo' }), 'repo');
  assert.equal(projectIdOrSelf('bare-name'), 'bare-name');
});
