import { describe, it, expect } from 'vitest';
import { buildEvaluationPayload } from './EvaluationForm.jsx';

const baseState = {
  repo: '/repos/myproject',
  selectedDims: new Set(['security', 'maintainability']),
  branch: null,
  scopePath: null,
  cleanScan: 'off',
};

describe('buildEvaluationPayload', () => {
  it('sets cleanScan: false and omits incremental when toggle is "off" (default)', () => {
    const payload = buildEvaluationPayload({ ...baseState, cleanScan: 'off' });
    expect(payload.cleanScan).toBe(false);
    expect(payload).not.toHaveProperty('incremental');
  });

  it('sets cleanScan: true when toggle is "once"', () => {
    const payload = buildEvaluationPayload({ ...baseState, cleanScan: 'once' });
    expect(payload.cleanScan).toBe(true);
    expect(payload).not.toHaveProperty('incremental');
  });

  it('sets cleanScan: true when toggle is "permanent"', () => {
    const payload = buildEvaluationPayload({ ...baseState, cleanScan: 'permanent' });
    expect(payload.cleanScan).toBe(true);
    expect(payload).not.toHaveProperty('incremental');
  });

  it('never includes an incremental field regardless of cleanScan value', () => {
    for (const val of ['off', 'once', 'permanent']) {
      const payload = buildEvaluationPayload({ ...baseState, cleanScan: val });
      expect(payload).not.toHaveProperty('incremental');
    }
  });

  it('omits dimensions when selectedDims is empty', () => {
    const payload = buildEvaluationPayload({ ...baseState, selectedDims: new Set() });
    expect(payload).not.toHaveProperty('dimensions');
  });

  it('includes dimensions as an array when selectedDims has values', () => {
    const payload = buildEvaluationPayload({ ...baseState });
    expect(Array.isArray(payload.dimensions)).toBe(true);
    expect(payload.dimensions).toEqual(expect.arrayContaining(['security', 'maintainability']));
    expect(payload.dimensions).toHaveLength(2);
  });

  it('includes branch when provided', () => {
    const payload = buildEvaluationPayload({ ...baseState, branch: 'feat/my-branch' });
    expect(payload.branch).toBe('feat/my-branch');
  });

  it('omits branch when null', () => {
    const payload = buildEvaluationPayload({ ...baseState, branch: null });
    expect(payload).not.toHaveProperty('branch');
  });

  it('includes scopePath when provided', () => {
    const payload = buildEvaluationPayload({ ...baseState, scopePath: 'src/api' });
    expect(payload.scopePath).toBe('src/api');
  });

  it('omits scopePath when null', () => {
    const payload = buildEvaluationPayload({ ...baseState, scopePath: null });
    expect(payload).not.toHaveProperty('scopePath');
  });

  it('includes repo from state', () => {
    const payload = buildEvaluationPayload({ ...baseState });
    expect(payload.repo).toBe('/repos/myproject');
  });
});
