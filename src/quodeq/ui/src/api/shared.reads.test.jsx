import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as shared from './shared.js';

/**
 * Split from shared.test.jsx: accumulated & scores, dimension eval &
 * violations, findings mirrors, and publish & pull.
 */

let calls;

beforeEach(() => {
  calls = [];
  vi.stubGlobal('fetch', vi.fn(async (url, opts) => {
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
  }));
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
  });
});
