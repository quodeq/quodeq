import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { useWorkspaceDiff } from './useWorkspaceDiff.js';

// fetchAssistantWorkspaceDiff/applyAssistantWorkspace/discardAssistantWorkspace
// can reject with a `code` (WORKSPACE_DIFF_FAILED, TURN_IN_PROGRESS,
// WORKSPACE_DISCARD_FAILED -- see assistant_workspace_routes.py, Task E5).
// Both loadDiff's and act's catch blocks used to render `err?.message ||
// String(err)` raw, ignoring that code entirely. Routed through
// apiErrorMessage now, matching the pattern already used by
// usePublish/useSessionLifecycle.
vi.mock('../../../strings/apiErrors.js', () => ({
  apiErrorMessage: vi.fn(() => 'MAPPED: friendly workspace failure'),
}));

// eslint-disable-next-line import/first -- must follow the vi.mock hoist above
import { apiErrorMessage } from '../../../strings/apiErrors.js';

function makeFakeApi(overrides = {}) {
  return {
    applyAssistantWorkspace: vi.fn(),
    createAssistantWorkspacePr: vi.fn(),
    discardAssistantWorkspace: vi.fn(),
    fetchAssistantWorkspaceDiff: vi.fn().mockResolvedValue({ diff: '', truncated: false }),
    ...overrides,
  };
}

describe('useWorkspaceDiff error mapping', () => {
  it('maps a failed diff load through apiErrorMessage', async () => {
    const err = new Error('boom');
    err.code = 'WORKSPACE_DIFF_FAILED';
    const fetchAssistantWorkspaceDiff = vi.fn().mockRejectedValue(err);
    const fakeApi = makeFakeApi({ fetchAssistantWorkspaceDiff });

    const { result } = renderHook(() => useWorkspaceDiff({ sessionId: 's1' }), {
      wrapper: ({ children }) => <ApiProvider value={fakeApi}>{children}</ApiProvider>,
    });

    await waitFor(() => expect(result.current.error).toBe('MAPPED: friendly workspace failure'));
    expect(apiErrorMessage).toHaveBeenCalledWith(err, 'assistant.diffLoadFailed');
  });

  it('maps a failed workspace action (apply/pr/discard) through apiErrorMessage', async () => {
    const err = new Error('a turn or workspace action is in progress; wait for it to finish');
    err.code = 'TURN_IN_PROGRESS';
    const applyAssistantWorkspace = vi.fn().mockRejectedValue(err);
    const fakeApi = makeFakeApi({ applyAssistantWorkspace });

    const { result } = renderHook(() => useWorkspaceDiff({ sessionId: 's1' }), {
      wrapper: ({ children }) => <ApiProvider value={fakeApi}>{children}</ApiProvider>,
    });
    await waitFor(() => expect(result.current.diff).not.toBeNull());

    await act(async () => {
      await result.current.act(() => applyAssistantWorkspace('s1'), 'applied');
    });

    expect(result.current.error).toBe('MAPPED: friendly workspace failure');
    expect(apiErrorMessage).toHaveBeenCalledWith(err, 'assistant.workspaceActionFailed');
  });
});
