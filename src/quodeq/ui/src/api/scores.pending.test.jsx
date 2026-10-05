import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getDashboard, getAccumulated, getProjectScores } from './scores.js';
import { sharedGetDashboard, sharedGetAccumulated, sharedGetProjectScores } from './sharedProjectData.js';
import { isPendingPayload } from './scoresShape.js';
import { request } from './request.js';

vi.mock('./request.js', () => ({ request: vi.fn() }));

// The server answers 202 with this body while its warm-up still owes the
// project. The fetchers hand it through untouched: wrapping it in a model
// would read as an empty project (no dimensions, no runs) instead of "not
// yet", and the hooks poll on the `pending` flag.
const PENDING = { pending: true, warmup: { active: true, projectsDone: 1, projectsTotal: 3, currentProjectName: 'quodeq' } };

describe('pending Overview payloads', () => {
  beforeEach(() => { request.mockReset(); request.mockResolvedValue({ ...PENDING }); });

  it.each([
    ['getDashboard', () => getDashboard('p1')],
    ['getAccumulated', () => getAccumulated('p1')],
    ['getProjectScores', () => getProjectScores('p1')],
    ['sharedGetDashboard', () => sharedGetDashboard('p1')],
    ['sharedGetAccumulated', () => sharedGetAccumulated('p1')],
    ['sharedGetProjectScores', () => sharedGetProjectScores('p1')],
  ])('%s passes a pending body through unchanged', async (_name, fetch) => {
    const data = await fetch();
    expect(data).toEqual(PENDING);
    expect(isPendingPayload(data)).toBe(true);
  });

  it('isPendingPayload is false for a real payload and for nothing', () => {
    expect(isPendingPayload({ dimensions: [] })).toBe(false);
    expect(isPendingPayload(null)).toBe(false);
    expect(isPendingPayload(undefined)).toBe(false);
  });
});
