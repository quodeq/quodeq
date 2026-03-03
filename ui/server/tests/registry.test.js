import test from 'node:test';
import assert from 'node:assert/strict';
import { getRegistry } from '../src/registry.js';

test('getRegistry returns a non-empty array', () => {
  const endpoints = getRegistry();
  assert.ok(Array.isArray(endpoints), 'should return an array');
  assert.ok(endpoints.length > 0, 'should not be empty');
});

test('every entry has the required fields', () => {
  const required = ['method', 'path', 'description', 'params', 'dataSource', 'response'];
  for (const entry of getRegistry()) {
    for (const field of required) {
      assert.ok(field in entry, `${entry.path ?? 'unknown'} missing field "${field}"`);
    }
  }
});

test('all paths start with /api', () => {
  for (const entry of getRegistry()) {
    assert.ok(entry.path.startsWith('/api'), `${entry.path} does not start with /api`);
  }
});

test('no duplicate method + path combinations', () => {
  const seen = new Set();
  for (const entry of getRegistry()) {
    const key = `${entry.method} ${entry.path}`;
    assert.ok(!seen.has(key), `duplicate entry: ${key}`);
    seen.add(key);
  }
});

test('self-referencing GET /api entry exists', () => {
  const self = getRegistry().find((e) => e.method === 'GET' && e.path === '/api');
  assert.ok(self, 'GET /api entry should be present');
  assert.ok(self.description.length > 0, 'description should not be empty');
});
