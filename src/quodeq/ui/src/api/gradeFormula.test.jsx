import { describe, it, expect, vi, beforeEach } from 'vitest';

import { resetGradeFormula } from './gradeFormula.js';

describe('resetGradeFormula', () => {
  let fetchCalls;

  beforeEach(() => {
    fetchCalls = [];
    vi.stubGlobal('fetch', vi.fn(async (url, opts) => {
      fetchCalls.push({ url, opts });
      return {
        ok: true,
        status: 200,
        json: async () => ({ current: {}, defaults: {}, isCustom: false, applied: 0 }),
      };
    }));
  });

  it('sends ?confirm=true on DELETE, matching the destructive-reset contract', async () => {
    await resetGradeFormula();
    expect(fetchCalls).toHaveLength(1);
    expect(fetchCalls[0].url).toBe('/api/grade-formula?confirm=true');
    expect(fetchCalls[0].opts.method).toBe('DELETE');
  });
});
