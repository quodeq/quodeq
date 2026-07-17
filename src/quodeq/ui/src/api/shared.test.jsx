import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as shared from './shared.js';

let calls;

beforeEach(() => {
  calls = [];
  globalThis.fetch = vi.fn(async (url, opts) => {
    calls.push({ url, opts });
    return {
      ok: true,
      json: async () => ({
        configured: true,
        url: 'https://github.com/test/repo.git',
        projects: [],
        runs: [],
        dimensions: [],
        summary: {},
        lastSynced: null,
        stale: false,
      }),
    };
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('shared repo API client', () => {
  describe('config management', () => {
    it('getSharedStatus GETs /shared/status', async () => {
      await shared.getSharedStatus();
      expect(calls[0].url).toBe('/api/shared/status');
      expect(calls[0].opts?.method).toBeUndefined();
    });

    it('connectShared PUTs /shared/config with url', async () => {
      await shared.connectShared('https://github.com/example/repo.git');
      expect(calls[0].url).toBe('/api/shared/config');
      expect(calls[0].opts.method).toBe('PUT');
      expect(JSON.parse(calls[0].opts.body)).toEqual({
        url: 'https://github.com/example/repo.git',
      });
    });

    it('disconnectShared DELETEs /shared/config', async () => {
      await shared.disconnectShared();
      expect(calls[0].url).toBe('/api/shared/config');
      expect(calls[0].opts.method).toBe('DELETE');
    });

    it('refreshShared POSTs /shared/refresh', async () => {
      await shared.refreshShared();
      expect(calls[0].url).toBe('/api/shared/refresh');
      expect(calls[0].opts.method).toBe('POST');
    });
  });

  describe('project listing & info', () => {
    it('sharedListProjects GETs /shared/projects with refresh=0 by default', async () => {
      await shared.sharedListProjects();
      expect(calls[0].url).toBe('/api/shared/projects?refresh=0');
      expect(calls[0].opts?.method).toBeUndefined();
    });

    it('sharedListProjects GETs /shared/projects with refresh=1 when requested', async () => {
      await shared.sharedListProjects({ refresh: true });
      expect(calls[0].url).toBe('/api/shared/projects?refresh=1');
    });

    it('sharedListProjects returns envelope with projects, lastSynced, and stale', async () => {
      globalThis.fetch = vi.fn(async () => {
        return {
          ok: true,
          json: async () => ({
            projects: [
              {
                id: 'proj1',
                name: 'Test Project',
                runsCount: undefined, // createProject should normalize to 0
                publishedBy: 'alice',
                publishedAt: '2026-07-17T10:00:00Z',
                source: 'shared',
              },
            ],
            lastSynced: '2026-07-17T10:30:00Z',
            stale: true,
          }),
        };
      });

      const result = await shared.sharedListProjects();

      // Assert envelope shape
      expect(result).toHaveProperty('projects');
      expect(result).toHaveProperty('lastSynced');
      expect(result).toHaveProperty('stale');

      // Assert sync metadata is carried through
      expect(result.lastSynced).toBe('2026-07-17T10:30:00Z');
      expect(result.stale).toBe(true);

      // Assert projects array and that createProject normalized runsCount
      expect(Array.isArray(result.projects)).toBe(true);
      expect(result.projects).toHaveLength(1);
      expect(result.projects[0].runsCount).toBe(0); // createProject normalizes missing runsCount to 0
      expect(result.projects[0].name).toBe('Test Project');

      // Assert shared-specific metadata is preserved
      expect(result.projects[0].publishedBy).toBe('alice');
      expect(result.projects[0].publishedAt).toBe('2026-07-17T10:00:00Z');
      expect(result.projects[0].source).toBe('shared');
    });

    it('sharedGetProjectInfo GETs /shared/projects/<id>/info', async () => {
      await shared.sharedGetProjectInfo('proj1');
      expect(calls[0].url).toBe('/api/shared/projects/proj1/info');
      expect(calls[0].opts?.method).toBeUndefined();
    });

    it('sharedGetProjectInfo encodes the project id', async () => {
      await shared.sharedGetProjectInfo('proj/with/slashes');
      expect(calls[0].url).toBe('/api/shared/projects/proj%2Fwith%2Fslashes/info');
    });
  });

  describe('runs & dashboard', () => {
    it('sharedGetRuns GETs /shared/projects/<id>/runs', async () => {
      await shared.sharedGetRuns('proj1');
      expect(calls[0].url).toBe('/api/shared/projects/proj1/runs');
    });

    it('sharedGetDashboard GETs /shared/projects/<id>/dashboard?run=...', async () => {
      await shared.sharedGetDashboard('proj1', 'latest');
      expect(calls[0].url).toBe('/api/shared/projects/proj1/dashboard?run=latest');
    });

    it('sharedGetDashboard defaults run to latest', async () => {
      await shared.sharedGetDashboard('proj1');
      expect(calls[0].url).toBe('/api/shared/projects/proj1/dashboard?run=latest');
    });

    it('sharedGetDashboard encodes run id', async () => {
      await shared.sharedGetDashboard('proj1', 'run/with/slashes');
      expect(calls[0].url).toBe('/api/shared/projects/proj1/dashboard?run=run%2Fwith%2Fslashes');
    });
  });

  describe('accumulated & scores', () => {
    it('sharedGetAccumulated GETs /shared/projects/<id>/accumulated without asOf', async () => {
      await shared.sharedGetAccumulated('proj1');
      expect(calls[0].url).toBe('/api/shared/projects/proj1/accumulated');
    });

    it('sharedGetAccumulated GETs /shared/projects/<id>/accumulated?asOf=... when provided', async () => {
      await shared.sharedGetAccumulated('proj1', 'run123');
      expect(calls[0].url).toBe('/api/shared/projects/proj1/accumulated?asOf=run123');
    });

    it('sharedGetProjectScores GETs /shared/projects/<id>/scores without asOf', async () => {
      await shared.sharedGetProjectScores('proj1');
      expect(calls[0].url).toBe('/api/shared/projects/proj1/scores');
    });

    it('sharedGetProjectScores GETs /shared/projects/<id>/scores?asOf=... when provided', async () => {
      await shared.sharedGetProjectScores('proj1', 'run123');
      expect(calls[0].url).toBe('/api/shared/projects/proj1/scores?asOf=run123');
    });

    it('sharedGetRunScores GETs /shared/projects/<id>/scores/<runId>', async () => {
      await shared.sharedGetRunScores('proj1', 'run123');
      expect(calls[0].url).toBe('/api/shared/projects/proj1/scores/run123');
    });

    it('sharedGetRunScores encodes both project and run', async () => {
      await shared.sharedGetRunScores('proj/1', 'run/123');
      expect(calls[0].url).toBe('/api/shared/projects/proj%2F1/scores/run%2F123');
    });
  });

  describe('dimension eval & violations', () => {
    it('sharedGetDimensionEval GETs /shared/projects/<id>/dimensions/<dim>/eval?run=...', async () => {
      await shared.sharedGetDimensionEval('proj1', 'run123', 'security');
      expect(calls[0].url).toBe('/api/shared/projects/proj1/dimensions/security/eval?run=run123');
    });

    it('sharedGetViolations GETs /shared/projects/<id>/violations?run=...', async () => {
      await shared.sharedGetViolations('proj1', 'run123');
      expect(calls[0].url).toBe('/api/shared/projects/proj1/violations?run=run123');
    });

    it('sharedGetViolations encodes both project and run', async () => {
      await shared.sharedGetViolations('proj/1', 'run/123');
      expect(calls[0].url).toBe('/api/shared/projects/proj%2F1/violations?run=run%2F123');
    });
  });

  describe('publish & pull', () => {
    it('publishProject POSTs /projects/<id>/publish', async () => {
      await shared.publishProject('proj1');
      expect(calls[0].url).toBe('/api/projects/proj1/publish');
      expect(calls[0].opts.method).toBe('POST');
    });

    it('publishProject encodes the project id', async () => {
      await shared.publishProject('proj/1');
      expect(calls[0].url).toBe('/api/projects/proj%2F1/publish');
    });

    it('pullSharedProject POSTs /shared/projects/<id>/pull without action', async () => {
      await shared.pullSharedProject('proj1');
      expect(calls[0].url).toBe('/api/shared/projects/proj1/pull');
      expect(calls[0].opts.method).toBe('POST');
      expect(JSON.parse(calls[0].opts.body)).toEqual({});
    });

    it('pullSharedProject POSTs /shared/projects/<id>/pull with action', async () => {
      await shared.pullSharedProject('proj1', 'copy');
      expect(calls[0].url).toBe('/api/shared/projects/proj1/pull');
      expect(calls[0].opts.method).toBe('POST');
      expect(JSON.parse(calls[0].opts.body)).toEqual({ action: 'copy' });
    });

    it('pullSharedProject encodes the project id', async () => {
      await shared.pullSharedProject('proj/1', 'copy');
      expect(calls[0].url).toBe('/api/shared/projects/proj%2F1/pull');
    });
  });
});
