import { describe, it, expect } from 'vitest';
import { buildScanPayload } from './ReEvaluateCard.jsx';

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
});
