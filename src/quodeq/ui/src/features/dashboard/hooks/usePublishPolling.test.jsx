import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { usePublishPolling } from './usePublishPolling.js';

// apiErrorMessage is mocked (rather than asserting a real mapped string) for
// a reason specific to this call site: the backend's publish-status payload
// (services/shared_publish.py's PublishStatus) never carries a `code` field
// today, only a plain `error` string. With no code, apiErrorMessage's own
// documented fallback order makes it produce byte-identical output to the
// OLD `publish.error || t('projects.publishFailed')` line for every
// possible input -- so a real (non-mocked) before/after comparison can never
// go RED. Mocking the mapper and asserting it was actually invoked (with the
// right shape) is what proves the wiring changed, independent of the two
// codepaths coincidentally agreeing on output today.
vi.mock('../../../strings/apiErrors.js', () => ({
  apiErrorMessage: vi.fn(() => 'MAPPED: friendly publish failure'),
}));

// eslint-disable-next-line import/first -- must follow the vi.mock hoist above
import { apiErrorMessage } from '../../../strings/apiErrors.js';

function setup(overrides = {}) {
  const getSharedStatus = vi.fn(async () => ({
    publish: { state: 'error', error: 'raw backend text', code: 'PUBLISH_START_FAILED' },
  }));
  const queryClient = { fetchQuery: vi.fn() };
  const mountedRef = { current: true };
  const { result } = renderHook(() => usePublishPolling({
    queryClient,
    sharedListProjects: vi.fn(),
    getSharedStatus,
    applyOptimisticPublish: vi.fn(),
    mountedRef,
    ...overrides,
  }));
  return { result, getSharedStatus };
}

describe('usePublishPolling', () => {
  it('publish error is mapped through apiErrorMessage', async () => {
    const { result } = setup();

    await act(async () => {
      await result.current.checkStatus();
    });

    // No `code` threaded through today (see file-level comment) -- the
    // mapper is called with just the raw message and the fallback key.
    expect(apiErrorMessage).toHaveBeenCalledWith({ message: 'raw backend text' }, 'projects.publishFailed');
    expect(result.current.publishError).toBe('MAPPED: friendly publish failure');
    expect(result.current.publishState).toBe('error');
  });
});
