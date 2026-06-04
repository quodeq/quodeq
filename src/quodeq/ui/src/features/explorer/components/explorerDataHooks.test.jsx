import React from 'react';
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiProvider } from '../../../api/ApiContext.jsx';
import { usePrincipleData } from './explorerDataHooks.js';

// ---------------------------------------------------------------------------
// Shared test fixtures
// ---------------------------------------------------------------------------

const EVAL_PRINCIPAL = {
  principle: 'Input Validation',
  dimension: 'Security',
  project: 'proj',
  runId: 'r1',
  principleData: { violations: [], compliance: [] },
  dimViolations: [],
  dimCompliance: [],
  score: '7.0/10',
  grade: 'B',
  dateLabel: '',
};

// Shape returned by POST /api/findings/dismiss with run_id supplied.
const DISMISS_RESPONSE = {
  scores: {
    dimensions: [{
      dimension: 'Security',
      overallScore: '6.0/10',
      overallGrade: 'C',
      principles: [{ principle: 'Input Validation', score: '6.5/10', grade: 'C+' }],
    }],
    summary: { overallGrade: 'C', numericAverage: 6.0 },
  },
};

// ---------------------------------------------------------------------------
// API mock — usePrincipleData no longer touches the API directly. It receives
// the dismiss handler from the caller (App.jsx) and treats its resolved value
// as the source of truth for the new score.
// ---------------------------------------------------------------------------

function wrapper({ children }) {
  return <ApiProvider value={{}}>{children}</ApiProvider>;
}

describe('usePrincipleData', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('updates liveScore/liveGrade from the dismiss response payload', async () => {
    const onDismiss = vi.fn(async () => DISMISS_RESPONSE);
    const { result } = renderHook(
      () => usePrincipleData(EVAL_PRINCIPAL, null, onDismiss),
      { wrapper },
    );

    await act(async () => {
      await result.current.handleDismiss({ file: 'a.py', line: 10, principle: 'Input Validation' });
    });

    expect(onDismiss).toHaveBeenCalledTimes(1);
    expect(result.current.liveScore).toBe('6.5/10');
    expect(result.current.liveGrade).toBe('C+');
  });

  it('keeps the violation in the dismissed set so it disappears from the list', async () => {
    const onDismiss = vi.fn(async () => DISMISS_RESPONSE);
    const { result } = renderHook(
      () => usePrincipleData(EVAL_PRINCIPAL, null, onDismiss),
      { wrapper },
    );

    await act(async () => {
      await result.current.handleDismiss({ file: 'a.py', line: 10, principle: 'Input Validation' });
    });

    expect(result.current.dismissedSet.has('a.py:10')).toBe(true);
  });

  it('rolls back the optimistic dismiss when the POST fails', async () => {
    const onDismiss = vi.fn(async () => { throw new Error('network down'); });
    const { result } = renderHook(
      () => usePrincipleData(EVAL_PRINCIPAL, null, onDismiss),
      { wrapper },
    );

    await act(async () => {
      await result.current.handleDismiss({ file: 'a.py', line: 10, principle: 'Input Validation' });
    });

    expect(onDismiss).toHaveBeenCalledTimes(1);
    expect(result.current.dismissedSet.has('a.py:10')).toBe(false);
    expect(result.current.liveScore).toBeNull();
    expect(result.current.liveGrade).toBeNull();
  });

  it('does nothing when no onDismiss prop is provided', async () => {
    const { result } = renderHook(
      () => usePrincipleData(EVAL_PRINCIPAL, null, null),
      { wrapper },
    );

    await act(async () => {
      await result.current.handleDismiss({ file: 'a.py', line: 10, principle: 'Input Validation' });
    });

    // No throw, no state change — the dismissed-set stays empty.
    expect(result.current.dismissedSet.size).toBe(0);
  });
});
