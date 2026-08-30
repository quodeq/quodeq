import test from 'node:test';
import assert from 'node:assert/strict';
import { classifyRepo, isLocalRepo } from './repo.js';

// ---------------------------------------------------------------------------
// classifyRepo / isLocalRepo -- pin the anchoring cases from EvaluationForm
// ---------------------------------------------------------------------------

test('classifyRepo: empty/falsy repo classifies as null', () => {
  assert.equal(classifyRepo(''), null);
  assert.equal(classifyRepo(null), null);
  assert.equal(classifyRepo(undefined), null);
});

test('classifyRepo: an https URL is remote', () => {
  assert.equal(classifyRepo('https://github.com/org/repo'), 'remote');
});

test('classifyRepo: an SSH git@ URL is remote', () => {
  assert.equal(classifyRepo('git@github.com:org/repo.git'), 'remote');
});

test('classifyRepo: a schemeless github.com paste is remote (anchored)', () => {
  assert.equal(classifyRepo('github.com/org/repo'), 'remote');
});

test('classifyRepo: a schemeless www.github.com paste is remote (anchored)', () => {
  assert.equal(classifyRepo('www.github.com/org/repo'), 'remote');
});

test('classifyRepo: a local path merely containing "github.com" is local -- anchoring must not match mid-string', () => {
  assert.equal(classifyRepo('/Users/me/projects/github.com-mirror/repo'), 'local');
});

test('classifyRepo: a plain local folder path is local', () => {
  assert.equal(classifyRepo('/Users/me/projects/my-repo'), 'local');
});

test('isLocalRepo: true for local paths, false for remote and empty', () => {
  assert.equal(isLocalRepo('/Users/me/projects/my-repo'), true);
  assert.equal(isLocalRepo('https://github.com/org/repo'), false);
  assert.equal(isLocalRepo(''), false);
});
