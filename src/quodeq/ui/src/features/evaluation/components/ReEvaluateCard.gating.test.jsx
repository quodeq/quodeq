import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { invalidateDimensionCache } from '../hooks/usePluginDimensions.js';
import { makeFakeApi, renderCard } from './_reEvaluateCard.fixtures.jsx';

/**
 * Split from ReEvaluateCard.test.jsx: ephemeral gating, clean-scan once
 * consumption, and the getProjectInfo error state.
 */

describe('ReEvaluateCard ephemeral gating', () => {
  beforeEach(() => {
    invalidateDimensionCache();
  });

  it('disables re-evaluation when projectInfo.evaluable is false (ephemeral completed)', async () => {
    const projectInfo = {
      name: 'demo',
      path: '/tmp/cloned/repo',
      location: 'local',
      ephemeral: true,
      evaluable: false,
    };
    const api = makeFakeApi({ getProjectInfo: vi.fn().mockResolvedValue(projectInfo) });
    renderCard({ project: 'uuid-1', projectInfo, api });

    // The explanatory note appears
    await waitFor(() => {
      expect(
        screen.getByText(/ephemeral|working copy was deleted|one-shot/i),
      ).toBeInTheDocument();
    });

    // The scan button should be disabled
    const button = screen.getByRole('button', { name: /^▸\s*scan$|^scan$|running\.\.\./i });
    expect(button).toBeDisabled();
  });

  it('keeps re-evaluation enabled for normal local projects', async () => {
    const projectInfo = {
      name: 'demo',
      path: '/repos/myproj',
      location: 'local',
      ephemeral: false,
      evaluable: true,
    };
    const api = makeFakeApi({
      getProjectInfo: vi.fn().mockResolvedValue(projectInfo),
      listStandards: vi.fn().mockResolvedValue([]),
    });
    renderCard({ project: 'uuid-2', projectInfo, api });

    // Wait for info to render (path appears in the identity strip's scope cell)
    await waitFor(() => {
      expect(screen.getByText(/\/repos\/myproj/)).toBeInTheDocument();
    });

    // No ephemeral note
    expect(
      screen.queryByText(/working copy was deleted|one-shot/i),
    ).not.toBeInTheDocument();

    // Scan button is not disabled
    const button = screen.getByRole('button', { name: /^▸\s*scan$|^scan$|running\.\.\./i });
    expect(button).not.toBeDisabled();
  });
});

describe('ReEvaluateCard clean-scan once consumption', () => {
  beforeEach(() => { invalidateDimensionCache(); });

  const localInfo = { name: 'demo', path: '/repos/myproj', location: 'local', ephemeral: false, evaluable: true };
  const apiWithDims = () => makeFakeApi({
    getProjectInfo: vi.fn().mockResolvedValue(localInfo),
    listPlugins: vi.fn().mockResolvedValue([{ dimensions: [
      { id: 'security', label: 'Security' },
    ] }]),
  });

  async function armOnceToggle(user) {
    await user.click(screen.getByRole('radio', { name: /clean scan/i }));
    expect(screen.getByRole('radio', { name: /clean scan/i })).toBeChecked();
    // Picking the clean card defaults to one-shot; the sub-choice reflects it.
    expect(screen.getByRole('button', { name: /this scan only/i })).toHaveAttribute('aria-pressed', 'true');
  }

  it('keeps the once toggle armed when the start is blocked', async () => {
    // Regression (v1.6.0): a start swallowed by the running-job guard still
    // consumed the one-shot clean toggle, so the user's retry silently ran
    // incremental and counted a discarded run's files as analyzed.
    const { default: userEvent } = await import('@testing-library/user-event');
    const user = userEvent.setup();
    const onStart = vi.fn().mockReturnValue(false);
    renderCard({ project: 'p-once', projectInfo: localInfo, api: apiWithDims(), onStart, preselectDims: ['security'] });
    await waitFor(() => expect(screen.getByRole('button', { name: /security/i })).toHaveAttribute('aria-pressed', 'true'));

    await armOnceToggle(user);
    await user.click(screen.getByRole('button', { name: /^▸\s*scan$|^scan$/i }));

    expect(onStart).toHaveBeenCalled();
    expect(screen.getByRole('radio', { name: /clean scan/i })).toBeChecked();
  });

  it('consumes the once toggle when the start goes through', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const user = userEvent.setup();
    const onStart = vi.fn().mockResolvedValue({ jobId: 'j1' });
    renderCard({ project: 'p-once2', projectInfo: localInfo, api: apiWithDims(), onStart, preselectDims: ['security'] });
    await waitFor(() => expect(screen.getByRole('button', { name: /security/i })).toHaveAttribute('aria-pressed', 'true'));

    await armOnceToggle(user);
    await user.click(screen.getByRole('button', { name: /^▸\s*scan$|^scan$/i }));

    await waitFor(() => {
      expect(screen.getByRole('radio', { name: /clean scan/i })).not.toBeChecked();
      expect(screen.getByRole('radio', { name: /incremental/i })).toBeChecked();
    });
  });
});

describe('ReEvaluateCard error state', () => {
  beforeEach(() => { invalidateDimensionCache(); });

  it('renders visible error UI instead of vanishing when getProjectInfo rejects', async () => {
    const api = makeFakeApi({ getProjectInfo: vi.fn().mockRejectedValue(new Error('boom')) });
    renderCard({ project: 'uuid-err', projectInfo: null, api });

    await waitFor(() => {
      expect(screen.getByText(/could not load project info/i)).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('retry re-invokes the info load', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const user = userEvent.setup();
    const getProjectInfo = vi.fn().mockRejectedValue(new Error('boom'));
    const api = makeFakeApi({ getProjectInfo });
    renderCard({ project: 'uuid-retry', projectInfo: null, api });

    await waitFor(() => {
      expect(screen.getByText(/could not load project info/i)).toBeInTheDocument();
    });
    expect(getProjectInfo).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole('button', { name: 'Retry' }));

    await waitFor(() => {
      expect(getProjectInfo).toHaveBeenCalledTimes(2);
    });
  });
});
