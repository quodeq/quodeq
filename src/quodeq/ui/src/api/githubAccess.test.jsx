import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { probeGit, getGithubAccount, startDeviceFlow, getDeviceFlow, pasteGithubToken, signOutGithub } from './githubAccess.js';

function okResponse(payload, status = 200) {
  return { ok: true, status, json: async () => payload };
}

describe('githubAccess api', () => {
  beforeEach(() => { vi.stubGlobal('fetch', vi.fn()); });
  afterEach(() => { vi.unstubAllGlobals(); });

  it('probeGit posts the url with a long timeout', async () => {
    fetch.mockResolvedValue(okResponse({ reachable: false, kind: 'not_found' }));
    const result = await probeGit('https://github.com/o/r.git');
    expect(result.kind).toBe('not_found');
    const [url, init] = fetch.mock.calls[0];
    expect(url).toMatch(/\/git\/probe$/);
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ url: 'https://github.com/o/r.git' });
  });

  it('account, device flow, token and sign-out hit their routes', async () => {
    fetch.mockResolvedValue(okResponse({}));
    await getGithubAccount();
    await startDeviceFlow();
    await getDeviceFlow();
    await pasteGithubToken('ghp_x');
    fetch.mockResolvedValue({ ok: true, status: 204, json: async () => { throw new Error('no body'); } });
    await signOutGithub();
    const calls = fetch.mock.calls.map(([u, i]) => `${i?.method || 'GET'} ${u.replace(/^.*\/api/, '')}`);
    expect(calls).toEqual([
      'GET /github/account', 'POST /github/device-flow', 'GET /github/device-flow',
      'POST /github/token', 'DELETE /github/account',
    ]);
    expect(JSON.parse(fetch.mock.calls[3][1].body)).toEqual({ token: 'ghp_x' });
  });
});
