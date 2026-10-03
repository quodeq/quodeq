import test from 'node:test';
import assert from 'node:assert/strict';
import { warnAndRethrow, runExclusive, toggleLogWindow } from './settingsHelpers.js';

function captureWarn(fn) {
  const calls = [];
  const original = console.warn;
  console.warn = (...args) => { calls.push(args); };
  return Promise.resolve()
    .then(fn)
    .finally(() => { console.warn = original; })
    .then(() => calls);
}

test('warnAndRethrow passes a resolved probe through without warning', async () => {
  const calls = await captureWarn(async () => {
    const probe = warnAndRethrow(async () => ({ recommended: 3 }), 'Ollama');
    assert.deepEqual(await probe(), { recommended: 3 });
  });
  assert.equal(calls.length, 0);
});

test('warnAndRethrow logs the provider label and rethrows the same error', async () => {
  const boom = new Error('down');
  const calls = await captureWarn(async () => {
    const probe = warnAndRethrow(async () => { throw boom; }, 'llama.cpp');
    await assert.rejects(probe(), (err) => err === boom);
  });
  assert.deepEqual(calls, [['llama.cpp concurrency test failed', boom]]);
});

test('runExclusive skips the task while another run holds the ref', async () => {
  const ref = { current: true };
  let ran = false;
  const result = await runExclusive(ref, async () => { ran = true; return 1; }, () => {});
  assert.equal(result, undefined);
  assert.equal(ran, false);
  assert.equal(ref.current, true);
});

test('runExclusive holds the ref during the task and returns its result', async () => {
  const ref = { current: false };
  const result = await runExclusive(ref, async () => {
    assert.equal(ref.current, true);
    return 'ok';
  }, () => {});
  assert.equal(result, 'ok');
  assert.equal(ref.current, false);
});

test('runExclusive reports a failure, rethrows it and releases the ref', async () => {
  const ref = { current: false };
  const boom = new Error('nope');
  const seen = [];
  await assert.rejects(runExclusive(ref, async () => { throw boom; }, (err) => seen.push(err)), (err) => err === boom);
  assert.deepEqual(seen, [boom]);
  assert.equal(ref.current, false);
});

test('toggleLogWindow closes an open log and opens a closed one', () => {
  const calls = [];
  const log = (open) => ({ open, openLog: () => calls.push('open'), closeLog: () => calls.push('close') });
  toggleLogWindow(log(true));
  toggleLogWindow(log(false));
  assert.deepEqual(calls, ['close', 'open']);
});
