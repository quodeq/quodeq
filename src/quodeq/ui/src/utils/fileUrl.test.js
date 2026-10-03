// node --test: `.test.js` files run under node:test, `.test.jsx` under vitest.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fileUrlFromPath, pathFromFileUrl } from './fileUrl.js';

test('fileUrlFromPath prefixes a posix path as is', () => {
  assert.equal(fileUrlFromPath('/Users/me/evals.git'), 'file:///Users/me/evals.git');
});

test('fileUrlFromPath adds the slash before a Windows drive and forward-slashes the path', () => {
  assert.equal(fileUrlFromPath('C:\\Users\\me\\evals.git'), 'file:///C:/Users/me/evals.git');
  assert.equal(fileUrlFromPath('d:/work/evals'), 'file:///d:/work/evals');
});

test('pathFromFileUrl returns the posix path and drops the slash before a Windows drive', () => {
  assert.equal(pathFromFileUrl('file:///Users/me/evals.git'), '/Users/me/evals.git');
  assert.equal(pathFromFileUrl('file:///C:/Users/me/evals.git'), 'C:/Users/me/evals.git');
});

test('pathFromFileUrl is empty for anything that is not a file url', () => {
  assert.equal(pathFromFileUrl('https://github.com/team/evaluations.git'), '');
  assert.equal(pathFromFileUrl(''), '');
  assert.equal(pathFromFileUrl(null), '');
});
