import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getDashboard } from './scores.js';
import { request } from './request.js';

vi.mock('./request.js', () => ({ request: vi.fn() }));

describe('getDashboard', () => {
  beforeEach(() => { request.mockReset(); request.mockResolvedValue({ dimensions: [], trend: [] }); });

  it('always asks for the overview shape', async () => {
    await getDashboard('p1', 'r1');
    expect(request).toHaveBeenCalledWith('/projects/p1/dashboard?run=r1&view=overview');
  });

  it('omits the run when falsy', async () => {
    await getDashboard('p1', null);
    expect(request).toHaveBeenCalledWith('/projects/p1/dashboard?view=overview');
  });

  it('defaults to the latest run', async () => {
    await getDashboard('p1');
    expect(request).toHaveBeenCalledWith('/projects/p1/dashboard?run=latest&view=overview');
  });
});
