import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { useSessionLifecycle } from './useSessionLifecycle.js';

// createAssistantSession's rejection carries a `code` (see api/request.js,
// which sets err.code from the JSON envelope's `code` field on any non-2xx
// response) whenever the backend used error_response(...) -- true for the
// shared-repo gate (NO_SHARED_REPO / SHARED_REPO_UNAVAILABLE, Task E5).
// commitSession's catch used to render `err?.message || err` raw, ignoring
// that code entirely. Routed through apiErrorMessage now, matching the
// pattern already used by usePublish/useSharedActions/useProjectActions.
vi.mock('../../../strings/apiErrors.js', () => ({
  apiErrorMessage: vi.fn(() => 'MAPPED: friendly session-start failure'),
}));

// eslint-disable-next-line import/first -- must follow the vi.mock hoist above
import { apiErrorMessage } from '../../../strings/apiErrors.js';

function makeFakeApi(overrides = {}) {
  return {
    createAssistantSession: vi.fn(),
    fetchAssistantWorkspace: vi.fn(),
    ...overrides,
  };
}

describe('useSessionLifecycle start-session error mapping', () => {
  it('maps a failed session start through apiErrorMessage', async () => {
    const err = new Error('shared repository unavailable: missing');
    err.code = 'SHARED_REPO_UNAVAILABLE';
    const createAssistantSession = vi.fn().mockRejectedValue(err);
    const fakeApi = makeFakeApi({ createAssistantSession });

    const { result } = renderHook(() => useSessionLifecycle(), {
      wrapper: ({ children }) => <ApiProvider value={fakeApi}>{children}</ApiProvider>,
    });

    await act(async () => {
      await result.current.startSession({ provider: 'claude', model: 'sonnet', projectId: 'p1', runId: 'r1', source: 'shared' });
    });

    expect(apiErrorMessage).toHaveBeenCalledWith(err, 'assistant.startSessionFailed');
    expect(result.current.localError).toBe("Couldn't start assistant session: MAPPED: friendly session-start failure");
  });
});
