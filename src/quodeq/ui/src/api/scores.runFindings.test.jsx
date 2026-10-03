import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getRunScores, getFindingDetail } from './scores.js';
import { sharedGetRunScores, sharedGetFindingDetail } from './sharedProjectData.js';
import { request } from './request.js';
import { PROJECT_SOURCE } from '../vocab/projectSource.js';

vi.mock('./request.js', () => ({ request: vi.fn() }));

const runPayload = () => ({
  dimensions: [{
    dimension: 'security',
    violations: [{ req: 'R1', file: 'a.py', line: 1, practiceId: 'P1', title: 'bad', detailDeferred: true }],
    compliance: [{ req: 'R1', file: 'b.py', line: 2, practiceId: 'P1', title: 'ok', detailDeferred: true }],
  }],
});

describe('getRunScores', () => {
  beforeEach(() => { request.mockReset(); request.mockResolvedValue(runPayload()); });

  it('tags each deferred item with a ref naming the run and the local source', async () => {
    const { dimensions: [dim] } = await getRunScores('p1', 'r1');
    expect(dim.violations[0].detailRef).toEqual({
      project: 'p1', run: 'r1', dimension: 'security', kind: 'violation', source: PROJECT_SOURCE.LOCAL, generation: expect.any(Number),
    });
    expect(dim.compliance[0].detailRef.kind).toBe('compliance');
    expect(dim.compliance[0].detailRef).not.toBe(dim.violations[0].detailRef);
  });

  it('shares one ref per dimension and kind, and numbers responses apart', async () => {
    request.mockResolvedValue({ dimensions: [{ dimension: 'security', violations: [
      { req: 'R1', file: 'a.py', line: 1, detailDeferred: true }, { req: 'R2', file: 'a.py', line: 9, detailDeferred: true },
    ] }] });
    const first = await getRunScores('p1', 'r1');
    const [a, b] = first.dimensions[0].violations;
    expect(a.detailRef).toBe(b.detailRef);
    request.mockResolvedValue(runPayload());
    const second = await getRunScores('p1', 'r1');
    expect(second.dimensions[0].violations[0].detailRef.generation).toBeGreaterThan(a.detailRef.generation);
  });

  it('leaves items with their detail alone', async () => {
    request.mockResolvedValue({ dimensions: [{ dimension: 'security', violations: [{ req: 'R1', file: 'a.py', line: 1, reason: 'why' }] }] });
    const { dimensions: [dim] } = await getRunScores('p1', 'r1');
    expect(dim.violations[0].detailRef).toBeUndefined();
  });
});

describe('sharedGetRunScores', () => {
  beforeEach(() => { request.mockReset(); request.mockResolvedValue(runPayload()); });

  it('tags deferred items with the shared source so hydration hits the mirror', async () => {
    const { dimensions: [dim] } = await sharedGetRunScores('p1', 'r1');
    expect(request).toHaveBeenCalledWith('/shared/projects/p1/scores/r1');
    expect(dim.violations[0].detailRef).toMatchObject({ project: 'p1', run: 'r1', source: PROJECT_SOURCE.SHARED });
  });
});

describe('getFindingDetail with a run', () => {
  beforeEach(() => { request.mockReset(); request.mockResolvedValue({ items: [] }); });

  it('asks /compliance-detail for that run', async () => {
    await getFindingDetail('p1', { kind: 'violation', dimension: 'security', run: 'r1', principle: 'P1' });
    expect(request).toHaveBeenCalledWith('/projects/p1/compliance-detail?dimension=security&kind=violation&run=r1&principle=P1');
  });

  it('never sends both asOf and run', async () => {
    await getFindingDetail('p1', { kind: 'violation', dimension: 'security', run: 'r1', asOf: 'r0' });
    expect(request.mock.calls[0][0]).not.toContain('asOf');
  });

  it('hits the shared mirror for shared projects', async () => {
    await sharedGetFindingDetail('p1', { kind: 'compliance', dimension: 'security', run: 'r1' });
    expect(request).toHaveBeenCalledWith('/shared/projects/p1/compliance-detail?dimension=security&kind=compliance&run=r1');
  });
});
