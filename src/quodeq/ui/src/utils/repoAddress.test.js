import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isUrlAddress, normalizeUrlAddress } from './repoAddress.js';

test('a scheme, an scp-style address or a user@host:path reads as a url', () => {
  for (const value of [
    'https://github.com/acme/billing.git', 'ssh://git@host/acme/billing', 'file:///Users/me/evals.git',
    'git@github.com:acme/billing.git', 'deploy@host.example:repos/billing',
  ]) assert.equal(isUrlAddress(value), true, value);
});

test('a host without a scheme reads as a url too', () => {
  assert.equal(isUrlAddress('github.com/org/repo'), true);
  assert.equal(isUrlAddress('gitlab.com/g/p.git'), true);
  assert.equal(isUrlAddress('  github.com/org/repo  '), true);
});

test('a path on this machine is not a url', () => {
  for (const value of ['/abs/path', './rel', '../up', '~/x', 'C:\\x', 'C:/x', 'plain-folder', 'with space.com/x', '']) {
    assert.equal(isUrlAddress(value), false, value);
  }
});

test('a host without a scheme is sent as https, anything else unchanged', () => {
  assert.equal(normalizeUrlAddress('github.com/org/repo'), 'https://github.com/org/repo');
  assert.equal(normalizeUrlAddress(' gitlab.com/g/p.git '), 'https://gitlab.com/g/p.git');
  assert.equal(normalizeUrlAddress('https://github.com/org/repo'), 'https://github.com/org/repo');
  assert.equal(normalizeUrlAddress('git@github.com:org/repo.git'), 'git@github.com:org/repo.git');
  assert.equal(normalizeUrlAddress('/abs/path'), '/abs/path');
});
