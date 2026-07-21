import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as shared from './shared.js';
import { createProject } from '../models/project.js';

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

    // The backend sends lastSynced as UNIX epoch SECONDS (st_mtime), not
    // milliseconds -- relativeTime()/`new Date()` expect ms, so passing
    // seconds straight through renders as a 1970 date ("57 years ago").
    it('getSharedStatus converts lastSynced from epoch seconds to epoch milliseconds', async () => {
      globalThis.fetch = vi.fn(async () => ({
        ok: true,
        json: async () => ({
          configured: true,
          url: 'https://github.com/test/repo.git',
          lastSynced: 1752751800, // realistic epoch-seconds fixture
          syncing: false,
          publish: { state: 'idle' },
        }),
      }));

      const result = await shared.getSharedStatus();

      expect(result.lastSynced).toBe(1752751800 * 1000);
    });

    it('getSharedStatus normalizes a null/absent lastSynced to null', async () => {
      globalThis.fetch = vi.fn(async () => ({
        ok: true,
        json: async () => ({ configured: false, url: null, lastSynced: null, publish: {} }),
      }));

      const result = await shared.getSharedStatus();

      expect(result.lastSynced).toBeNull();
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
    it('createProject carries originUrl through, defaulting to null when absent', () => {
      expect(createProject({ name: 'x', originUrl: 'u' }).originUrl).toBe('u');
      expect(createProject({ name: 'x' }).originUrl).toBeNull();
    });

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
      // Realistic epoch-SECONDS fixtures (git log %ct / st_mtime), matching
      // what the backend actually sends on the wire -- the client is
      // expected to convert these to epoch-milliseconds before returning.
      const publishedAtSeconds = 1752750000;
      const lastSyncedSeconds = 1752751800;
      globalThis.fetch = vi.fn(async () => {
        return {
          ok: true,
          json: async () => ({
            projects: [
              {
                id: 'proj1',
                name: 'Test Project',
                runsCount: undefined, // createProject should normalize to 0
                originUrl: 'https://github.com/org/app.git',
                publishedBy: 'alice',
                publishedAt: publishedAtSeconds,
                source: 'shared',
              },
            ],
            lastSynced: lastSyncedSeconds,
            stale: true,
          }),
        };
      });

      const result = await shared.sharedListProjects();

      // Assert envelope shape
      expect(result).toHaveProperty('projects');
      expect(result).toHaveProperty('lastSynced');
      expect(result).toHaveProperty('stale');

      // Assert sync metadata is carried through, converted to milliseconds
      expect(result.lastSynced).toBe(lastSyncedSeconds * 1000);
      expect(result.stale).toBe(true);

      // Assert projects array and that createProject normalized runsCount
      expect(Array.isArray(result.projects)).toBe(true);
      expect(result.projects).toHaveLength(1);
      expect(result.projects[0].runsCount).toBe(0); // createProject normalizes missing runsCount to 0
      expect(result.projects[0].name).toBe('Test Project');
      expect(result.projects[0].originUrl).toBe('https://github.com/org/app.git');

      // Assert shared-specific metadata is preserved, publishedAt converted to milliseconds
      expect(result.projects[0].publishedBy).toBe('alice');
      expect(result.projects[0].publishedAt).toBe(publishedAtSeconds * 1000);
      expect(result.projects[0].source).toBe('shared');
    });

    it('sharedListProjects normalizes a null/absent publishedAt and lastSynced to null', async () => {
      globalThis.fetch = vi.fn(async () => ({
        ok: true,
        json: async () => ({
          projects: [{ id: 'proj1', name: 'Test Project', publishedAt: null, source: 'shared' }],
          lastSynced: null,
          stale: false,
        }),
      }));

      const result = await shared.sharedListProjects();

      expect(result.lastSynced).toBeNull();
      expect(result.projects[0].publishedAt).toBeNull();
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

    // Finding 5 (final whole-branch review): createProject() only knows the
    // base Project shape and silently drops publishedBy/publishedAt/source --
    // without passing them through explicitly (same idiom as
    // sharedListProjects above), the Overview's shared-project hero badge has
    // no "published by <name>" to show. publishedAt also needs the same
    // epoch-seconds -> epoch-milliseconds conversion as every other shared
    // timestamp.
    it('sharedGetProjectInfo passes through publishedBy and converts publishedAt to epoch milliseconds', async () => {
      globalThis.fetch = vi.fn(async () => ({
        ok: true,
        json: async () => ({
          id: 'proj1', name: 'proj1', publishedBy: 'ana', publishedAt: 1752751800, source: 'shared',
        }),
      }));

      const result = await shared.sharedGetProjectInfo('proj1');

      expect(result.publishedBy).toBe('ana');
      expect(result.publishedAt).toBe(1752751800 * 1000);
      expect(result.source).toBe('shared');
    });

    it('sharedGetProjectInfo normalizes a missing publishedBy/publishedAt to null', async () => {
      globalThis.fetch = vi.fn(async () => ({
        ok: true,
        json: async () => ({ id: 'proj1', name: 'proj1' }),
      }));

      const result = await shared.sharedGetProjectInfo('proj1');

      expect(result.publishedBy).toBeNull();
      expect(result.publishedAt).toBeNull();
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

  describe('findings (read-only mirrors)', () => {
    it('sharedListDismissedFindings GETs /shared/projects/<id>/findings/dismissed with a limit', async () => {
      await shared.sharedListDismissedFindings('proj1');
      expect(calls[0].url).toBe('/api/shared/projects/proj1/findings/dismissed?limit=5000');
      expect(calls[0].opts?.method).toBeUndefined();
    });

    it('sharedListDismissedFindings encodes the project id', async () => {
      await shared.sharedListDismissedFindings('proj/1');
      expect(calls[0].url).toBe('/api/shared/projects/proj%2F1/findings/dismissed?limit=5000');
    });

    it('sharedListVerifiedFindings GETs /shared/projects/<id>/findings/verified', async () => {
      await shared.sharedListVerifiedFindings('proj1');
      expect(calls[0].url).toBe('/api/shared/projects/proj1/findings/verified');
      expect(calls[0].opts?.method).toBeUndefined();
    });

    it('sharedListVerifiedFindings encodes the project id', async () => {
      await shared.sharedListVerifiedFindings('proj/1');
      expect(calls[0].url).toBe('/api/shared/projects/proj%2F1/findings/verified');
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

    // The online Projects tab's "pull local copy" footer action needs to
    // detect a 409 collision (same contract as the manual import flow) and
    // offer an inline "copy" confirm -- it can only do that if the thrown
    // Error carries status/kind/existingProjectId, which the generic
    // request() helper does not attach.
    it('pullSharedProject throws an Error carrying status/kind/existingProjectId on a 409 collision', async () => {
      globalThis.fetch = vi.fn(async () => ({
        ok: false,
        status: 409,
        json: async () => ({
          error: 'Project already exists',
          code: 'PROJECT_EXISTS',
          kind: 'same_uuid',
          existingProjectId: 'abc-123',
          projectName: 'demo-repo',
        }),
      }));
      await expect(shared.pullSharedProject('proj1')).rejects.toMatchObject({
        status: 409,
        code: 'PROJECT_EXISTS',
        kind: 'same_uuid',
        existingProjectId: 'abc-123',
        projectName: 'demo-repo',
      });
    });
  });
});
