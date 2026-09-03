import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('registerProject', () => {
  let registerProject;
  let fetchCalls;

  beforeEach(async () => {
    // Reset fetch tracking
    fetchCalls = [];
    global.fetch = vi.fn(async (url, opts) => {
      fetchCalls.push(url);
      return {
        ok: true,
        status: 201,
        json: async () => ({ projectId: 'p1', scanData: {} }),
      };
    });
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('calls fetch with the BASE-prefixed URL (default /api base)', async () => {
    // With default VITE_API_BASE (unset), BASE should be '/api'
    const { registerProject: fn } = await import('./projects.js');
    registerProject = fn;

    await registerProject({ repo: 'https://example.com/repo.git' });
    expect(fetchCalls[0]).toBe('/api/projects');
  });

  it('calls fetch with the BASE-prefixed URL (custom base)', async () => {
    // Override VITE_API_BASE and re-import to pick up the new value
    vi.stubEnv('VITE_API_BASE', '/custom-api');

    // Clear the module cache so we get a fresh import with the new env
    vi.resetModules();

    const { registerProject: fn } = await import('./projects.js');
    registerProject = fn;

    await registerProject({ repo: 'https://example.com/repo.git' });
    expect(fetchCalls[0]).toBe('/custom-api/projects');
  });
});
