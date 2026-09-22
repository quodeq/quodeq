import { describe, it, expect } from 'vitest';
import { buildScanPayload } from './ReEvaluateCard.jsx';

/**
 * Split from ReEvaluateCard.test.jsx: pure buildScanPayload() tests.
 */

const baseState = {
  info: { path: '/repos/myproject' },
  branch: null,
  scopePath: null,
  selectedDims: new Set(['security', 'maintainability']),
  cleanScan: 'off',
};

describe('buildScanPayload', () => {
  it('sets cleanScan: false and omits incremental when toggle is "off" (default)', () => {
    const payload = buildScanPayload({ ...baseState, cleanScan: 'off' });
    expect(payload.cleanScan).toBe(false);
    expect(payload).not.toHaveProperty('incremental');
  });

  it('sets cleanScan: true when toggle is "once"', () => {
    const payload = buildScanPayload({ ...baseState, cleanScan: 'once' });
    expect(payload.cleanScan).toBe(true);
    expect(payload).not.toHaveProperty('incremental');
  });

  it('sets cleanScan: true when toggle is "permanent"', () => {
    const payload = buildScanPayload({ ...baseState, cleanScan: 'permanent' });
    expect(payload.cleanScan).toBe(true);
    expect(payload).not.toHaveProperty('incremental');
  });

  it('includes repo path from info', () => {
    const payload = buildScanPayload({ ...baseState });
    expect(payload.repo).toBe('/repos/myproject');
  });

  it('includes selected dimensions as an array', () => {
    const payload = buildScanPayload({ ...baseState });
    expect(payload.dimensions).toEqual(['security', 'maintainability']);
  });

  it('includes branch when provided', () => {
    const payload = buildScanPayload({ ...baseState, branch: 'feat/my-branch' });
    expect(payload.branch).toBe('feat/my-branch');
  });

  it('omits branch when null', () => {
    const payload = buildScanPayload({ ...baseState, branch: null });
    expect(payload).not.toHaveProperty('branch');
  });

  it('includes scopePath when provided', () => {
    const payload = buildScanPayload({ ...baseState, scopePath: 'src/api' });
    expect(payload.scopePath).toBe('src/api');
  });

  it('omits scopePath when null', () => {
    const payload = buildScanPayload({ ...baseState, scopePath: null });
    expect(payload).not.toHaveProperty('scopePath');
  });

  it('carries the launching project id as uiProject', () => {
    // The in-progress card labels itself with the job's own project; the
    // launching project id bridges the gap until the backend resolves it.
    const payload = buildScanPayload({ ...baseState, project: 'uuid-x' });
    expect(payload.uiProject).toBe('uuid-x');
  });

  it('omits uiProject when no project is known', () => {
    const payload = buildScanPayload({ ...baseState });
    expect(payload).not.toHaveProperty('uiProject');
  });

  it('carries the per-run time budget, including 0 for no limit', () => {
    expect(buildScanPayload({ ...baseState, timeLimitS: 600 }).timeLimit).toBe(600);
    // 0 must survive: preparePayload treats a present timeLimit as
    // authoritative, and 0 means "no limit" — not "use Settings".
    expect(buildScanPayload({ ...baseState, timeLimitS: 0 }).timeLimit).toBe(0);
  });

  it('omits timeLimit when no budget was chosen', () => {
    expect(buildScanPayload({ ...baseState })).not.toHaveProperty('timeLimit');
  });
});
