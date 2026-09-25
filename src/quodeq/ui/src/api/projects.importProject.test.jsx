import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Characterizes importProject's request/response contract before it moves
// onto the shared request() wrapper: a multipart body with no forced
// Content-Type, no internal timeout (large zips can take a while), and the
// 409-collision error fields (status/code/kind/existingProjectId/projectName)
// a caller reads to offer Replace / Import as copy / Cancel.
describe('importProject', () => {
  let fetchCalls;

  beforeEach(() => {
    fetchCalls = [];
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends a multipart body with the file (and action, when given), no JSON Content-Type', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url, opts) => {
      fetchCalls.push([url, opts]);
      return { ok: true, status: 200, json: async () => ({ imported: true, projectId: 'p1' }) };
    }));
    const { importProject } = await import('./projects.js');
    const file = new Blob(['zip-bytes']);
    await importProject(file, { action: 'replace' });

    const [url, opts] = fetchCalls[0];
    expect(url).toBe('/api/projects/import');
    expect(opts.method).toBe('POST');
    expect(opts.body).toBeInstanceOf(FormData);
    expect(opts.body.get('file')).toBeInstanceOf(Blob);
    expect(await opts.body.get('file').text()).toBe(await file.text());
    expect(opts.body.get('action')).toBe('replace');
    expect(opts.headers?.['Content-Type']).toBeUndefined();
  });

  it('omits the action field when none is given', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url, opts) => {
      fetchCalls.push([url, opts]);
      return { ok: true, status: 200, json: async () => ({ imported: true, projectId: 'p1' }) };
    }));
    const { importProject } = await import('./projects.js');
    await importProject(new Blob(['x']));
    expect(fetchCalls[0][1].body.get('action')).toBeNull();
  });

  it('throws with status/code/kind/existingProjectId/projectName on a 409 collision', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false,
      status: 409,
      json: async () => ({
        error: 'project already imported',
        code: 'PROJECT_EXISTS',
        kind: 'same_uuid',
        existingProjectId: 'p0',
        projectName: 'demo',
      }),
    })));
    const { importProject } = await import('./projects.js');
    let caught;
    try {
      await importProject(new Blob(['x']));
    } catch (err) {
      caught = err;
    }
    expect(caught).toBeDefined();
    expect(caught.status).toBe(409);
    expect(caught.code).toBe('PROJECT_EXISTS');
    expect(caught.kind).toBe('same_uuid');
    expect(caught.existingProjectId).toBe('p0');
    expect(caught.projectName).toBe('demo');
  });

  it('synthesises a message when the envelope carries none', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) })));
    const { importProject } = await import('./projects.js');
    await expect(importProject(new Blob(['x']))).rejects.toThrow();
  });
});
