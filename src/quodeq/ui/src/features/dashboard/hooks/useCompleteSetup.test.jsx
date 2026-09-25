import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { useCompleteSetup } from './useCompleteSetup.js';

/**
 * useCompleteSetup backs IncompleteSetupCard's re-registration flow: it
 * must call registerProject through the injected ApiContext (never a direct
 * api/index.js import) so the card can be tested without hitting fetch.
 */
function wrapper(api) {
  return function Wrapper({ children }) {
    return <ApiProvider value={api}>{children}</ApiProvider>;
  };
}

describe('useCompleteSetup', () => {
  it('calls registerProject (from useApi()) with the repo url and clone target', async () => {
    const registerProject = vi.fn().mockResolvedValue({ projectId: 'p1', scanData: {} });
    const onComplete = vi.fn();
    const { result } = renderHook(
      () => useCompleteSetup({ repoUrl: 'https://x/y.git', onComplete }),
      { wrapper: wrapper({ registerProject }) },
    );

    await act(async () => {
      await result.current.handleSubmit({ cloneDest: '/tmp/x', ephemeral: false });
    });

    expect(registerProject).toHaveBeenCalledWith({ repo: 'https://x/y.git', cloneDest: '/tmp/x', ephemeral: false });
    expect(onComplete).toHaveBeenCalledWith({ projectId: 'p1', scanData: {} });
    expect(result.current.submitting).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('sets a friendly error and does not call onComplete on failure', async () => {
    const registerProject = vi.fn().mockRejectedValue(Object.assign(new Error('boom'), { code: 'REGISTRATION_FAILED' }));
    const onComplete = vi.fn();
    const { result } = renderHook(
      () => useCompleteSetup({ repoUrl: 'https://x/y.git', onComplete }),
      { wrapper: wrapper({ registerProject }) },
    );

    await act(async () => {
      await result.current.handleSubmit({ cloneDest: '/tmp/x' });
    });

    expect(onComplete).not.toHaveBeenCalled();
    expect(result.current.error).toBeTruthy();
    expect(result.current.submitting).toBe(false);
  });

  it('open toggles independently, starting closed', () => {
    const registerProject = vi.fn();
    const { result } = renderHook(
      () => useCompleteSetup({ repoUrl: 'x', onComplete: vi.fn() }),
      { wrapper: wrapper({ registerProject }) },
    );
    expect(result.current.open).toBe(false);
    act(() => result.current.setOpen(true));
    expect(result.current.open).toBe(true);
  });
});
