import test from 'node:test';
import assert from 'node:assert/strict';
import { bootTheme } from './bootTheme.js';

test('bootTheme: a throwing applyTheme is caught and logged, not propagated', () => {
  const boom = new Error('theme apply blocked');
  const warnCalls = [];
  const originalWarn = console.warn;
  console.warn = (...args) => warnCalls.push(args);
  try {
    assert.doesNotThrow(() => bootTheme(() => { throw boom; }));
  } finally {
    console.warn = originalWarn;
  }
  assert.equal(warnCalls.length, 1);
  assert.match(warnCalls[0][0], /^\[main\]/);
  assert.equal(warnCalls[0][1], boom);
});

test('bootTheme: a succeeding applyTheme does not warn', () => {
  const warnCalls = [];
  const originalWarn = console.warn;
  console.warn = (...args) => warnCalls.push(args);
  let called = false;
  try {
    bootTheme(() => { called = true; });
  } finally {
    console.warn = originalWarn;
  }
  assert.equal(called, true);
  assert.equal(warnCalls.length, 0);
});
