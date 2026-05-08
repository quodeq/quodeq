import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import RepoScanStep from './RepoScanStep.jsx';

const noop = () => {};

describe('RepoScanStep', () => {
  it('idle state renders the repo input and Scan repository button', () => {
    render(<RepoScanStep state={{ repoScanSubState: 'idle', repo: { value: '' } }} actions={{ setRepo: noop, startScan: noop, succeedScan: noop, failScan: noop, resetScan: noop }} createProject={noop} onContinue={noop} onCancel={noop} />);
    expect(screen.getByPlaceholderText(/git@github.com/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /scan repository/i })).toBeInTheDocument();
  });

  it('scanned state renders the summary with file count', () => {
    render(<RepoScanStep
      state={{ repoScanSubState: 'scanned', repo: { value: '/p' }, scan: { total_files: 42, languages: { py: 10 }, branches: ['main'], modules: [] } }}
      actions={{ setRepo: noop, startScan: noop, succeedScan: noop, failScan: noop, resetScan: noop }}
      createProject={noop}
      onContinue={noop}
      onCancel={noop}
    />);
    expect(screen.getByText('42')).toBeInTheDocument();
    expect(screen.getByText('FILES')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /continue/i })).toBeInTheDocument();
  });

  it('error state renders Try again and Edit repository actions', () => {
    render(<RepoScanStep
      state={{ repoScanSubState: 'error', repo: { value: '/bad' }, scanError: { message: 'not found' } }}
      actions={{ setRepo: noop, startScan: noop, succeedScan: noop, failScan: noop, resetScan: noop }}
      createProject={noop}
      onContinue={noop}
      onCancel={noop}
    />);
    expect(screen.getByText(/not found/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /edit repository/i })).toBeInTheDocument();
  });

  it('submitting the form calls createProject and dispatches success on resolve', async () => {
    const startScan = vi.fn();
    const succeedScan = vi.fn();
    const failScan = vi.fn();
    const setRepo = vi.fn();
    const createProject = vi.fn().mockResolvedValue({ projectId: 'uuid-9', scanData: { total_files: 7 } });

    render(<RepoScanStep
      state={{ repoScanSubState: 'idle', repo: { value: '/some/path' } }}
      actions={{ setRepo, startScan, succeedScan, failScan, resetScan: noop }}
      createProject={createProject}
      onContinue={noop}
      onCancel={noop}
    />);
    fireEvent.click(screen.getByRole('button', { name: /scan repository/i }));
    await waitFor(() => expect(createProject).toHaveBeenCalledWith({ repo: '/some/path' }));
    expect(startScan).toHaveBeenCalled();
    await waitFor(() => expect(succeedScan).toHaveBeenCalledWith('uuid-9', { total_files: 7 }));
  });

  it('createProject rejection dispatches failScan with the error', async () => {
    const startScan = vi.fn();
    const failScan = vi.fn();
    const createProject = vi.fn().mockRejectedValue(Object.assign(new Error('boom'), { status: 400 }));
    render(<RepoScanStep
      state={{ repoScanSubState: 'idle', repo: { value: '/some/path' } }}
      actions={{ setRepo: noop, startScan, succeedScan: noop, failScan, resetScan: noop }}
      createProject={createProject}
      onContinue={noop}
      onCancel={noop}
    />);
    fireEvent.click(screen.getByRole('button', { name: /scan repository/i }));
    await waitFor(() => expect(failScan).toHaveBeenCalled());
    expect(failScan.mock.calls[0][0].message).toBe('boom');
  });

  it('409 with no evaluations on the existing project silently resumes into it', async () => {
    const succeedScan = vi.fn();
    const failScan = vi.fn();
    const createProject = vi.fn().mockRejectedValue(
      Object.assign(new Error('already added'), { status: 409, existingProjectId: 'uuid-existing' }),
    );
    const getProjectInfo = vi.fn().mockResolvedValue({ id: 'uuid-existing', runsCount: 0 });
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ total_files: 12, languages: { py: 12 }, branches: ['main'], modules: [] }),
    });
    try {
      render(<RepoScanStep
        state={{ repoScanSubState: 'idle', repo: { value: '/some/path' } }}
        actions={{ setRepo: noop, startScan: noop, succeedScan, failScan, resetScan: noop }}
        createProject={createProject}
        getProjectInfo={getProjectInfo}
        onContinue={noop}
        onCancel={noop}
      />);
      fireEvent.click(screen.getByRole('button', { name: /scan repository/i }));
      await waitFor(() => expect(succeedScan).toHaveBeenCalled());
      expect(succeedScan).toHaveBeenCalledWith('uuid-existing', expect.objectContaining({ total_files: 12 }));
      expect(failScan).not.toHaveBeenCalled();
    } finally {
      fetchSpy.mockRestore();
    }
  });

  it('routes URL input through CloneTargetStep instead of calling createProject directly', async () => {
    const createProject = vi.fn().mockResolvedValue({ projectId: 'uuid-9', scanData: { total_files: 7 } });
    render(
      <RepoScanStep
        state={{ repoScanSubState: 'idle', repo: { value: 'https://github.com/x/y.git' } }}
        actions={{ setRepo: noop, startScan: noop, succeedScan: noop, failScan: noop, resetScan: noop }}
        createProject={createProject}
        onContinue={noop}
        onCancel={noop}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: /scan/i }));
    // We should NOT call createProject yet — instead, see CloneTargetStep
    expect(createProject).not.toHaveBeenCalled();
    expect(await screen.findByText(/where should we clone this repo/i)).toBeInTheDocument();
  });

  it('local path input continues to call createProject directly', async () => {
    const createProject = vi.fn().mockResolvedValue({ projectId: 'uuid-9', scanData: { total_files: 7 } });
    render(
      <RepoScanStep
        state={{ repoScanSubState: 'idle', repo: { value: '/tmp/repo' } }}
        actions={{ setRepo: noop, startScan: noop, succeedScan: noop, failScan: noop, resetScan: noop }}
        createProject={createProject}
        onContinue={noop}
        onCancel={noop}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: /scan/i }));
    await waitFor(() => expect(createProject).toHaveBeenCalledWith({ repo: '/tmp/repo' }));
  });

  it('CloneTargetStep submission forwards cloneDest to createProject', async () => {
    const createProject = vi.fn().mockResolvedValue({ projectId: 'uuid-9', scanData: { total_files: 7 } });
    render(
      <RepoScanStep
        state={{ repoScanSubState: 'idle', repo: { value: 'https://github.com/x/y.git' } }}
        actions={{ setRepo: noop, startScan: noop, succeedScan: noop, failScan: noop, resetScan: noop }}
        createProject={createProject}
        onContinue={noop}
        onCancel={noop}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: /scan/i }));
    await screen.findByText(/where should we clone this repo/i);
    const input = await screen.findByLabelText(/clone destination/i);
    fireEvent.change(input, { target: { value: '/Users/v/code' } });
    fireEvent.click(screen.getByRole('button', { name: /clone and scan/i }));
    await waitFor(() => expect(createProject).toHaveBeenCalledWith({
      repo: 'https://github.com/x/y.git',
      cloneDest: '/Users/v/code',
      ephemeral: false,
    }));
  });

  it('back button on CloneTargetStep returns to URL input form', async () => {
    render(
      <RepoScanStep
        state={{ repoScanSubState: 'idle', repo: { value: 'https://github.com/x/y.git' } }}
        actions={{ setRepo: noop, startScan: noop, succeedScan: noop, failScan: noop, resetScan: noop }}
        createProject={vi.fn()}
        onContinue={noop}
        onCancel={noop}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: /scan/i }));
    await screen.findByText(/where should we clone this repo/i);
    fireEvent.click(screen.getByRole('button', { name: /^back$/i }));
    // After back, the URL input form is shown again
    await screen.findByDisplayValue('https://github.com/x/y.git');
  });

  it('persists cloneDest to localStorage on successful non-ephemeral submission', async () => {
    const createProject = vi.fn().mockResolvedValue({ projectId: 'uuid', scanData: {} });
    localStorage.removeItem('quodeq.lastCloneRoot');
    render(
      <RepoScanStep
        state={{ repoScanSubState: 'idle', repo: { value: 'https://github.com/x/y.git' } }}
        actions={{ setRepo: noop, startScan: noop, succeedScan: noop, failScan: noop, resetScan: noop }}
        createProject={createProject}
        onContinue={noop}
        onCancel={noop}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: /scan/i }));
    await screen.findByText(/where should we clone this repo/i);
    fireEvent.change(screen.getByLabelText(/clone destination/i), { target: { value: '/Users/v/code' } });
    fireEvent.click(screen.getByRole('button', { name: /clone and scan/i }));
    await waitFor(() => expect(createProject).toHaveBeenCalled());
    expect(localStorage.getItem('quodeq.lastCloneRoot')).toBe('/Users/v/code');
  });

  it('does not persist localStorage when ephemeral is true', async () => {
    const createProject = vi.fn().mockResolvedValue({ projectId: 'uuid', scanData: {} });
    localStorage.removeItem('quodeq.lastCloneRoot');
    render(
      <RepoScanStep
        state={{ repoScanSubState: 'idle', repo: { value: 'https://github.com/x/y.git' } }}
        actions={{ setRepo: noop, startScan: noop, succeedScan: noop, failScan: noop, resetScan: noop }}
        createProject={createProject}
        onContinue={noop}
        onCancel={noop}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: /scan/i }));
    await screen.findByText(/where should we clone this repo/i);
    fireEvent.click(screen.getByRole('button', { name: /just run one evaluation/i }));
    await waitFor(() => expect(createProject).toHaveBeenCalled());
    expect(localStorage.getItem('quodeq.lastCloneRoot')).toBeNull();
  });

  it('shows actionable message when clone fails with AUTH_REQUIRED', async () => {
    const err = Object.assign(new Error('git clone failed (auth)'), { code: 'AUTH_REQUIRED' });
    const createProject = vi.fn().mockRejectedValue(err);
    render(
      <RepoScanStep
        state={{ repoScanSubState: 'idle', repo: { value: 'https://github.com/x/y.git' } }}
        actions={{ setRepo: noop, startScan: noop, succeedScan: noop, failScan: noop, resetScan: noop }}
        createProject={createProject}
        onContinue={noop}
        onCancel={noop}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: /scan/i }));
    await screen.findByText(/where should we clone this repo/i);
    fireEvent.change(screen.getByLabelText(/clone destination/i), { target: { value: '/Users/v/code' } });
    fireEvent.click(screen.getByRole('button', { name: /clone and scan/i }));
    expect(await screen.findByText(/private repo/i)).toBeInTheDocument();
  });

  it('409 with evaluations on the existing project surfaces the error normally', async () => {
    const succeedScan = vi.fn();
    const failScan = vi.fn();
    const createProject = vi.fn().mockRejectedValue(
      Object.assign(new Error('already added'), { status: 409, existingProjectId: 'uuid-existing' }),
    );
    const getProjectInfo = vi.fn().mockResolvedValue({ id: 'uuid-existing', runsCount: 3 });
    render(<RepoScanStep
      state={{ repoScanSubState: 'idle', repo: { value: '/some/path' } }}
      actions={{ setRepo: noop, startScan: noop, succeedScan, failScan, resetScan: noop }}
      createProject={createProject}
      getProjectInfo={getProjectInfo}
      onContinue={noop}
      onCancel={noop}
    />);
    fireEvent.click(screen.getByRole('button', { name: /scan repository/i }));
    await waitFor(() => expect(failScan).toHaveBeenCalled());
    expect(failScan.mock.calls[0][0]).toMatchObject({
      status: 409,
      existingProjectId: 'uuid-existing',
    });
    expect(succeedScan).not.toHaveBeenCalled();
  });
});
