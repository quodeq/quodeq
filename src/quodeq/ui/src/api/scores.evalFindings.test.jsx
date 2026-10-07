import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getDimensionEval } from './scores.js';
import { sharedGetDimensionEval } from './sharedProjectData.js';
import { request } from './request.js';
import { PROJECT_SOURCE } from '../vocab/projectSource.js';

vi.mock('./request.js', () => ({ request: vi.fn() }));

const deferred = (file, title) => ({ practiceId: 'P1', file, line: 1, title, severity: 'major', detailDeferred: true });

const evalPayload = () => ({
  dimension: 'security', runId: 'r1', project: 'p1',
  principles: [{ name: 'P1' }],
  violations: [deferred('a.py', 'bad')],
  compliance: [deferred('b.py', 'ok')],
  principleGrades: [],
});

describe('getDimensionEval', () => {
  beforeEach(() => { request.mockReset(); request.mockResolvedValue(evalPayload()); });

  it('tags the flat lists with a ref naming the run, the dimension and the local source', async () => {
    const data = await getDimensionEval('p1', 'r1', 'security');
    expect(data.violations[0].detailRef).toEqual({
      project: 'p1', run: 'r1', dimension: 'security', kind: 'violation', source: PROJECT_SOURCE.LOCAL,
    });
    expect(data.compliance[0].detailRef.kind).toBe('compliance');
    expect(data.compliance[0].detailRef).not.toBe(data.violations[0].detailRef);
  });

  it('leaves a live eval, sent with its detail, alone', async () => {
    request.mockResolvedValue({ ...evalPayload(), violations: [{ practiceId: 'P1', file: 'a.py', line: 1, reason: 'why' }] });
    const data = await getDimensionEval('p1', 'r1', 'security');
    expect(data.violations[0].detailRef).toBeUndefined();
    expect(data.violations[0].reason).toBe('why');
  });

  it('gives two responses for the same run equal refs, so one detail query serves both', async () => {
    const first = await getDimensionEval('p1', 'r1', 'security');
    request.mockResolvedValue(evalPayload());
    const second = await getDimensionEval('p1', 'r1', 'security');
    expect(second.violations[0].detailRef).toEqual(first.violations[0].detailRef);
  });
});

describe('sharedGetDimensionEval', () => {
  beforeEach(() => { request.mockReset(); request.mockResolvedValue(evalPayload()); });

  it('tags deferred items with the shared source so hydration hits the mirror', async () => {
    const data = await sharedGetDimensionEval('p1', 'r1', 'security');
    expect(request).toHaveBeenCalledWith('/shared/projects/p1/dimensions/security/eval?run=r1');
    expect(data.violations[0].detailRef).toMatchObject({ project: 'p1', run: 'r1', source: PROJECT_SOURCE.SHARED });
  });
});
