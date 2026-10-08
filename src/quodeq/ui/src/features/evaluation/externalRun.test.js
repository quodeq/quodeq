import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isExternal, isDiffReview, diffFileCount, checksPassed, githubCommitUrl } from './externalRun.js';

const diff = { dimensions: [
  { id: 'security', estimateReason: 'diff', files: { total: 12 }, compliance: 9 },
  { id: 'performance', estimateReason: 'diff', files: { total: 7 }, compliance: 4 },
] };

test('an external job is one the app did not start', () => {
  assert.equal(isExternal({ source: 'external' }), true);
  assert.equal(isExternal({ source: 'internal' }), false);
  assert.equal(isExternal(null), false);
});

test('a diff review is recognised from the progress estimate reason', () => {
  assert.equal(isDiffReview(diff), true);
  assert.equal(isDiffReview({ dimensions: [{ estimateReason: 'first-run' }] }), false);
  assert.equal(isDiffReview(null), false);
});

test('diff file count is the widest dimension, checks passed the sum', () => {
  assert.equal(diffFileCount(diff), 12);
  assert.equal(diffFileCount({ dimensions: [] }), null);
  assert.equal(checksPassed(diff), 13);
  assert.equal(checksPassed({ dimensions: [{ compliance: null }] }), 0);
});

test('open on GitHub points at the commit for github origins only', () => {
  const sha = '7e506ae';
  assert.equal(githubCommitUrl('https://github.com/quodeq/quodeq.git', sha), 'https://github.com/quodeq/quodeq/commit/7e506ae');
  assert.equal(githubCommitUrl('git@github.com:quodeq/quodeq.git', sha), 'https://github.com/quodeq/quodeq/commit/7e506ae');
  assert.equal(githubCommitUrl('https://gitlab.com/a/b', sha), null);
  assert.equal(githubCommitUrl('https://github.com/quodeq/quodeq', null), null);
  assert.equal(githubCommitUrl('https://github.com/quodeq/quodeq', 'main; rm'), null);
});

test('the scan mode of a diff review is diff', async () => {
  const { deriveScanMode } = await import('./components/jobStatCells/derivations.js');
  const { SCAN_MODE } = await import('./components/scanModes.js');
  assert.equal(deriveScanMode(diff), SCAN_MODE.DIFF);
  assert.equal(SCAN_MODE.DIFF, 'diff');
});
