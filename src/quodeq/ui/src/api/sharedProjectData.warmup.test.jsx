import { describe, it, expect, vi, beforeEach } from 'vitest';
import { sharedListProjects } from './sharedProjectData.js';
import { request } from './request.js';

vi.mock('./request.js', () => ({ request: vi.fn() }));

// The server keeps a card off the listing until its worker has warmed it and
// counts the rest in `warmup`. The fetcher rebuilds the envelope by hand, so
// the block has to be carried across on purpose: without it the page shows
// the first card and never learns that more are on their way.
describe('sharedListProjects warm-up envelope', () => {
  beforeEach(() => { request.mockReset(); });

  it('carries the warmup block through', async () => {
    const warmup = { active: true, projectsDone: 1, projectsTotal: 4, currentProjectName: 'two' };
    request.mockResolvedValue({ projects: [{ id: 'p1', name: 'one' }], lastSynced: 1752710400, stale: false, warmup });
    const data = await sharedListProjects();
    expect(data.warmup).toEqual(warmup);
    expect(data.projects.map((p) => p.id)).toEqual(['p1']);
  });

  it('is null when the server sent no warm-up', async () => {
    request.mockResolvedValue({ projects: [], lastSynced: null, stale: false });
    expect((await sharedListProjects()).warmup).toBeNull();
  });
});
