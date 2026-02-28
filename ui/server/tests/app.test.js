import test from 'node:test';
import assert from 'node:assert/strict';
import { createApp, proxyToActionApi } from '../src/app.js';

test('forwards api requests to action api', async () => {
  const originalFetch = global.fetch;
  global.fetch = async (url, options) => ({
    status: 200,
    headers: new Map([['content-type', 'application/json']]),
    text: async () => JSON.stringify({ ok: true, url, method: options.method })
  });

  const req = {
    originalUrl: '/api/projects',
    method: 'GET',
    body: null
  };

  let resolve;
  const done = new Promise((r) => { resolve = r; });
  const res = {
    statusCode: null,
    headers: {},
    body: null,
    status(code) { this.statusCode = code; return this; },
    set(name, value) { this.headers[name] = value; return this; },
    send(payload) { this.body = payload; resolve(); },
    json(payload) { this.body = JSON.stringify(payload); resolve(); }
  };

  try {
    await proxyToActionApi(req, res, 'http://127.0.0.1:9999');
    await done;
    const parsed = JSON.parse(res.body);
    assert.equal(res.statusCode, 200);
    assert.equal(parsed.ok, true);
    assert.equal(parsed.method, 'GET');
  } finally {
    global.fetch = originalFetch;
  }
});

test('serves static root even when action api proxy is enabled', async () => {
  const app = createApp({
    staticDistPath: '/tmp/codecompass-static',
    actionApiBase: 'http://127.0.0.1:9999',
    jobManager: {}
  });

  const stack = app._router?.stack ?? [];
  const hasStatic = stack.some((layer) => layer.name === 'serveStatic');
  assert.equal(hasStatic, true);
});
