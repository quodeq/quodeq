import { describe, it, expect, vi } from 'vitest';
import { makeHandleSubmit } from './useRepoScanStep.js';
import { apiErrorMessage } from '../../../strings/apiErrors.js';

// The direct path (a local path, or a repo already registered under a
// createProject call that isn't the clone-target sub-step) used to hand
// failScan the raw err.message instead of routing it through the same
// friendly mapper every other call site uses. `.jsx` because this hook
// pulls in the api layer, which relies on import.meta.env -- plain
// `node --test` can't load it, so this runs under vitest (`npm run test:ui`).

describe('makeHandleSubmit', () => {
  it('direct-path scan failure runs the error through apiErrorMessage', async () => {
    // AUTH_REQUIRED is a mapped code, so its friendly text diverges from the
    // raw backend message -- that divergence is what makes this test fail
    // against the old `message: err.message` code.
    const err = Object.assign(new Error('raw internal detail'), { code: 'AUTH_REQUIRED' });
    const createProject = vi.fn().mockRejectedValue(err);
    const actions = { startScan: vi.fn(), failScan: vi.fn(), succeedScan: vi.fn() };
    const handleSubmit = makeHandleSubmit({
      state: { repo: { value: 'org/repo' } },
      actions,
      createProject,
      setSubStep: vi.fn(),
      setCloneError: vi.fn(),
      tryResumeExisting: vi.fn().mockResolvedValue(false),
    });

    await handleSubmit();

    expect(actions.failScan).toHaveBeenCalledWith(
      expect.objectContaining({ message: apiErrorMessage(err, 'onboarding.scanFailed') }),
    );
    expect(actions.failScan.mock.calls[0][0].message).not.toBe(err.message);
  });

  it('an unmapped code keeps showing the backend message, unchanged', async () => {
    const err = Object.assign(new Error('Project not found'), { code: 'NOT_FOUND' });
    const createProject = vi.fn().mockRejectedValue(err);
    const actions = { startScan: vi.fn(), failScan: vi.fn(), succeedScan: vi.fn() };
    const handleSubmit = makeHandleSubmit({
      state: { repo: { value: 'org/repo' } },
      actions,
      createProject,
      setSubStep: vi.fn(),
      setCloneError: vi.fn(),
      tryResumeExisting: vi.fn().mockResolvedValue(false),
    });

    await handleSubmit();

    expect(actions.failScan.mock.calls[0][0].message).toBe('Project not found');
  });
});
