import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isCloningProject } from './cloningProject.js';

const local = { id: 'p1', path: '/Users/me/quodeq/repos/billing', originUrl: 'https://github.com/acme/billing.git' };

test('matches the running clone by id, by origin url (scheme, case and .git aside), or by folder', () => {
  assert.equal(isCloningProject(local, { projectId: 'p1' }), true);
  assert.equal(isCloningProject(local, { repo: 'HTTPS://github.com/acme/billing' }), true);
  assert.equal(isCloningProject(local, { repo: 'git@github.com:acme/other.git', dest: '/Users/me/quodeq/repos/billing' }), true);
  // A symlinked root: the record's path is resolved, the slot's is not.
  assert.equal(isCloningProject(local, { repo: 'https://github.com/acme/other', dest: '/tmp/repos/billing' }), true);
});

test('does not match another project, and never without a slot or a project', () => {
  assert.equal(isCloningProject(local, { projectId: 'p2', repo: 'https://github.com/acme/ledger.git', dest: '/u/repos/ledger' }), false);
  assert.equal(isCloningProject(local, null), false);
  assert.equal(isCloningProject(null, { dest: '/u/repos/billing' }), false);
});
