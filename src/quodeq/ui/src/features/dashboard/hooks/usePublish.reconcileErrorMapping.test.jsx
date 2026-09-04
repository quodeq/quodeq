import { describe, it, expect, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { usePublish } from './usePublish.js';
import { withStableQueryApi } from '../../../test-utils/withQueryClient.jsx';

// Same rationale as usePublishPolling.test.jsx: services/shared_publish.py's
// PublishStatus never carries a `code` field, only a plain `error` string.
// With no code, apiErrorMessage's documented fallback order makes it produce
// byte-identical output to the OLD `publish.error || t('projects.publishFailed')`
// line for every possible input -- so a real (non-mocked) before/after
// comparison can never go RED here either. Mocking the mapper and asserting
// it was actually invoked (with the right shape) is what proves the
// reconciliation branch's wiring changed, independent of the two codepaths
// coincidentally agreeing on output today.
vi.mock('../../../strings/apiErrors.js', () => ({
  apiErrorMessage: vi.fn(() => 'MAPPED: friendly publish failure'),
}));

// eslint-disable-next-line import/first -- must follow the vi.mock hoist above
import { apiErrorMessage } from '../../../strings/apiErrors.js';

function makeFakeApi(overrides = {}) {
  return {
    getSharedStatus: vi.fn(async () => ({
      configured: true,
      url: 'https://github.com/team/results.git',
      publish: { state: 'idle', project: null, runs: null, error: null, finishedAt: null },
    })),
    sharedListProjects: vi.fn(async () => ({ projects: [], lastSynced: null, stale: false })),
    publishProject: vi.fn(async () => ({ started: true })),
    ...overrides,
  };
}

const makeStableWrapper = withStableQueryApi;

describe('usePublish reconciliation error mapping', () => {
  // Mirrors usePublish.reconcileAndLifecycle.test.jsx's "reconciles to error
  // and surfaces it when the job failed while disabled" scenario, but proves
  // the mount-time reconciliation path (useReconcilePublishStatus) routes
  // through apiErrorMessage exactly like the polling path (checkStatus)
  // already does since D17.
  it('maps a reconciled publish error through apiErrorMessage', async () => {
    const getSharedStatus = vi.fn(async () => ({
      configured: true,
      publish: { state: 'running', project: 'p1' },
    }));
    const fakeApi = makeFakeApi({ getSharedStatus });
    const { result, rerender } = renderHook(
      ({ enabled }) => usePublish({ enabled }),
      {
        wrapper: makeStableWrapper(fakeApi),
        initialProps: { enabled: true },
      }
    );

    await waitFor(() => expect(result.current.publishState).toBe('running'));

    await act(async () => {
      rerender({ enabled: false });
    });

    // The job fails server-side while the hook is disabled -- surfaced by
    // useReconcilePublishStatus (not the poller) on re-enable.
    getSharedStatus.mockImplementation(async () => ({
      configured: true,
      publish: { state: 'error', project: 'p1', error: 'raw backend text' },
    }));

    await act(async () => {
      rerender({ enabled: true });
    });

    await waitFor(() => expect(result.current.publishState).toBe('error'));

    // No `code` threaded through today (see file-level comment) -- the
    // mapper is called with just the raw message and the fallback key.
    expect(apiErrorMessage).toHaveBeenCalledWith({ message: 'raw backend text' }, 'projects.publishFailed');
    expect(result.current.publishError).toBe('MAPPED: friendly publish failure');
    expect(result.current.publishErrorProject).toBe('p1');
  });
});
