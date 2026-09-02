import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as shared from './shared.js';

/**
 * Split from shared.test.jsx: accumulated & scores, dimension eval &
 * violations, findings mirrors, and publish & pull.
 */

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

    it('pullSharedProject passes an abort signal and maps a timeout to a clear error', async () => {
      await shared.pullSharedProject('proj1');
      expect(calls[0].opts.signal).toBeInstanceOf(AbortSignal);
      const timeoutErr = new Error('signal timed out');
      timeoutErr.name = 'TimeoutError';
      globalThis.fetch = vi.fn(async () => { throw timeoutErr; });
      await expect(shared.pullSharedProject('proj1')).rejects.toThrow(/timed out/i);
    });
  });
});
