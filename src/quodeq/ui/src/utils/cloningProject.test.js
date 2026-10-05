import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isCloningProject } from './cloningProject.js';

const local = { id: 'p1', path: '/Users/me/quodeq/repos/billing', originUrl: 'https://github.com/acme/billing.git' };

test('matches the running clone by id, by origin url (scheme, case and .git aside), or by folder', () => {
  assert.equal(isCloningProject(local, { projectId: 'p1' }), true);
  assert.equal(isCloningProject(local, { repo: 'HTTPS://github.com/acme/billing' }), true);
  assert.equal(isCloningProject(local, { repo: 'git@github.com:acme/other.git', dest: '/Users/me/quodeq/repos/billing' }), true);
  // A symlinked root: the record's path is resolved, the slot's is not.
  assert.equal(isCloningProject(local, { repo: 'https://github.com/acme/billing', dest: '/tmp/repos/billing' }), true);
  assert.equal(isCloningProject({ ...local, originUrl: undefined }, { repo: 'https://github.com/acme/other', dest: '/tmp/repos/billing' }), true);
});

test('an ssh and an https address of the same repository are one remote', () => {
  assert.equal(isCloningProject({ ...local, path: '/elsewhere/billing' }, { repo: 'git@github.com:acme/billing.git' }), true);
  assert.equal(isCloningProject({ ...local, path: '/elsewhere/billing' }, { repo: 'ssh://git@github.com/acme/billing' }), true);
});

test('a folder with the same name but another remote is a different project', () => {
  const work = { id: 'x', path: '/Users/me/work/api', originUrl: 'https://github.com/mine/api.git' };
  assert.equal(isCloningProject(work, { repo: 'https://github.com/other/api', dest: '/Users/me/quodeq/repos/api' }), false);
});

test('does not match another project, and never without a slot or a project', () => {
  assert.equal(isCloningProject(local, { projectId: 'p2', repo: 'https://github.com/acme/ledger.git', dest: '/u/repos/ledger' }), false);
  assert.equal(isCloningProject(local, null), false);
  assert.equal(isCloningProject(null, { dest: '/u/repos/billing' }), false);
});
