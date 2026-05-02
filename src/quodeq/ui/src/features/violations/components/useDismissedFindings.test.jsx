import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, act, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { useDismissedFindings } from './useDismissedFindings.js';

vi.mock('../../../api/index.js', () => ({
  listDismissedFindings: vi.fn(),
  restoreFinding: vi.fn(),
  restoreAllFindings: vi.fn(),
}));

import {
  listDismissedFindings,
  restoreFinding,
  restoreAllFindings,
} from '../../../api/index.js';

const sampleA = { req: 'A1', file: 'a.py', line: 10, severity: 'minor' };
const sampleB = { req: 'B1', file: 'b.py', line: 20, severity: 'major' };

function HookHarness({ project, onRefresh, setRestoreError, onState }) {
  const state = useDismissedFindings(project, onRefresh, setRestoreError);
  React.useEffect(() => { onState(state); }, [state, onState]);
  return null;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useDismissedFindings — restore handlers', () => {
  it('handleRestore removes the matching entry on success and calls onRefresh', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA, sampleB]);
    restoreFinding.mockResolvedValueOnce({ ok: true });
    const onRefresh = vi.fn();
    const setRestoreError = vi.fn();
    let latest;
    render(
      <HookHarness
        project="proj"
        onRefresh={onRefresh}
        setRestoreError={setRestoreError}
        onState={(s) => { latest = s; }}
      />,
    );
    await waitFor(() => expect(latest.dismissed).toHaveLength(2));

    await act(async () => { await latest.handleRestore(sampleA); });

    expect(restoreFinding).toHaveBeenCalledWith('proj', { req: 'A1', file: 'a.py', line: 10 });
    expect(latest.dismissed).toEqual([sampleB]);
    expect(onRefresh).toHaveBeenCalledTimes(1);
    expect(setRestoreError).not.toHaveBeenCalled();
  });

  it('handleRestore reports an error and leaves state unchanged on failure', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA]);
    restoreFinding.mockRejectedValueOnce(new Error('boom'));
    const onRefresh = vi.fn();
    const setRestoreError = vi.fn();
    let latest;
    render(
      <HookHarness
        project="proj"
        onRefresh={onRefresh}
        setRestoreError={setRestoreError}
        onState={(s) => { latest = s; }}
      />,
    );
    await waitFor(() => expect(latest.dismissed).toHaveLength(1));

    await act(async () => { await latest.handleRestore(sampleA); });

    expect(setRestoreError).toHaveBeenCalledWith('Failed to restore finding. Please try again.');
    expect(latest.dismissed).toEqual([sampleA]);
    expect(onRefresh).not.toHaveBeenCalled();
  });

  it('handleRestoreAll clears state on success and calls onRefresh', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA, sampleB]);
    restoreAllFindings.mockResolvedValueOnce({ ok: true, restored: 2 });
    const onRefresh = vi.fn();
    const setRestoreError = vi.fn();
    let latest;
    render(
      <HookHarness
        project="proj"
        onRefresh={onRefresh}
        setRestoreError={setRestoreError}
        onState={(s) => { latest = s; }}
      />,
    );
    await waitFor(() => expect(latest.dismissed).toHaveLength(2));

    await act(async () => { await latest.handleRestoreAll(); });

    expect(restoreAllFindings).toHaveBeenCalledWith('proj');
    expect(latest.dismissed).toEqual([]);
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });
});
