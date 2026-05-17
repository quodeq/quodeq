import React from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { MockEventSource } from '../../../test-utils/MockEventSource.js';
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

const RESCORE_RESPONSE = {
  dimensions: [{
    dimension: 'Security',
    overallScore: '7.5/10',
    overallGrade: 'B+',
    principles: [{ principle: 'Input Validation', score: '8.0/10', grade: 'A-' }],
  }],
  summary: { overallGrade: 'B+', numericAverage: 7.5 },
};

// ---------------------------------------------------------------------------
// API mock
// ---------------------------------------------------------------------------

const getRunScoresMock = vi.fn(async () => RESCORE_RESPONSE);
const fakeApi = { getRunScores: getRunScoresMock };

function wrapper({ children }) {
  return <ApiProvider value={fakeApi}>{children}</ApiProvider>;
}

// ---------------------------------------------------------------------------
// EventSource / flag lifecycle
// ---------------------------------------------------------------------------

describe('usePrincipleData', () => {
  let originalEventSource;

  beforeEach(() => {
    originalEventSource = global.EventSource;
    global.EventSource = MockEventSource;
    MockEventSource.last = null;
    getRunScoresMock.mockClear();
  });

  afterEach(() => {
    global.EventSource = originalEventSource;
    vi.clearAllMocks();
  });

  it('does NOT call getRunScores after dismiss', async () => {
    const onDismiss = vi.fn();
    const { result } = renderHook(
      () => usePrincipleData(EVAL_PRINCIPAL, null, onDismiss),
      { wrapper },
    );

    // Wait for the hook to stabilise (EventSource created by useGradeStream).
    await waitFor(() => expect(MockEventSource.last).not.toBeNull());

    await act(async () => {
      result.current.handleDismiss({ file: 'a.py', line: 10, principle: 'Input Validation' });
    });

    // onDismiss forwarded, but getRunScores must NOT have been called.
    expect(onDismiss).toHaveBeenCalledTimes(1);
    expect(getRunScoresMock).not.toHaveBeenCalled();
  });

  it('updates liveScore and liveGrade from useGradeStream payload', async () => {
    const { result } = renderHook(
      () => usePrincipleData(EVAL_PRINCIPAL, null, vi.fn()),
      { wrapper },
    );

    // Wait until useGradeStream has opened the EventSource connection.
    await waitFor(() => expect(MockEventSource.last).not.toBeNull());

    const payload = {
      dimensions: [{
        dimension: 'Security',
        overallScore: '6.0/10',
        overallGrade: 'C',
        principles: [{ principle: 'Input Validation', score: '6.5/10', grade: 'C+' }],
      }],
      summary: { overallGrade: 'C', numericAverage: 6.0 },
    };

    act(() => {
      MockEventSource.last.emit('scores.updated', payload);
    });

    await waitFor(() => {
      expect(result.current.liveScore).toBe('6.5/10');
      expect(result.current.liveGrade).toBe('C+');
    });
  });
});
