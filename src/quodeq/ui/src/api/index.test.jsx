import { describe, it, expect, vi, beforeEach } from 'vitest';
import { registerProject } from './index.js';

beforeEach(() => {
  global.fetch = vi.fn();
});

describe('registerProject', () => {
  it('forwards cloneDest and ephemeral when provided', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ projectId: 'u', scanData: {} }),
    });
    await registerProject({ repo: 'https://x/y.git', cloneDest: '/tmp', ephemeral: false });
    const [, opts] = global.fetch.mock.calls[0];
    const body = JSON.parse(opts.body);
    expect(body.repo).toBe('https://x/y.git');
    expect(body.cloneDest).toBe('/tmp');
    expect(body.ephemeral).toBe(false);
  });

  it('omits cloneDest when ephemeral=true', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ projectId: 'u', scanData: {} }),
    });
    await registerProject({ repo: 'https://x/y.git', ephemeral: true });
    const body = JSON.parse(global.fetch.mock.calls[0][1].body);
    expect(body.ephemeral).toBe(true);
  });

  it('omits both for plain local-path call', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ projectId: 'u', scanData: {} }),
    });
    await registerProject({ repo: '/tmp/repo' });
    const body = JSON.parse(global.fetch.mock.calls[0][1].body);
    expect(body.repo).toBe('/tmp/repo');
    expect(body.cloneDest).toBeUndefined();
    expect(body.ephemeral).toBeUndefined();
  });

  it('throws Error with code attached when response is not ok', async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ error: 'cloneDest is required', code: 'MISSING_CLONE_DEST' }),
    });
    let caught;
    try {
      await registerProject({ repo: 'https://x/y.git' });
    } catch (err) {
      caught = err;
    }
    expect(caught).toBeDefined();
    expect(caught.code).toBe('MISSING_CLONE_DEST');
    expect(caught.status).toBe(400);
  });
});
