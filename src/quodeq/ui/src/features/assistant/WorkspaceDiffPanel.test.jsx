import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../api/assistant.js', () => ({
  fetchAssistantWorkspaceDiff: vi.fn().mockResolvedValue({
    diff: 'diff --git a/x b/x\n@@ -1 +1 @@\n-a\n+b\n', stats: [{ file: 'x', added: 1, deleted: 1 }],
  }),
  applyAssistantWorkspace: vi.fn().mockResolvedValue({ applied: true, stats: [] }),
  createAssistantWorkspacePr: vi.fn().mockResolvedValue({ prUrl: 'http://pr/1', branch: 'b', pushed: true, message: 'PR created' }),
  discardAssistantWorkspace: vi.fn().mockResolvedValue({ discarded: true }),
}));
vi.mock('../../utils/confirmDialog.js', () => ({ confirmDialog: vi.fn() }));

import { applyAssistantWorkspace, discardAssistantWorkspace } from '../../api/assistant.js';
import { confirmDialog } from '../../utils/confirmDialog.js';
import { ApiProvider } from '../../api/ApiContext.jsx';
import { WorkspaceDiffPanel, classifyDiffLine } from './WorkspaceDiffPanel.jsx';

function makeFakeApi(overrides = {}) {
  return {
    fetchAssistantWorkspaceDiff: vi.fn().mockResolvedValue({
      diff: 'diff --git a/x b/x\n@@ -1 +1 @@\n-a\n+b\n', truncated: false, stats: [],
    }),
    applyAssistantWorkspace: vi.fn().mockResolvedValue({ applied: true, stats: [] }),
    createAssistantWorkspacePr: vi.fn().mockResolvedValue({
      prUrl: 'http://pr/1', branch: 'b', pushed: true, message: 'PR created',
    }),
    discardAssistantWorkspace: vi.fn().mockResolvedValue({ discarded: true }),
    ...overrides,
  };
}

describe('classifyDiffLine', () => {
  it('classifies diff lines', () => {
    expect(classifyDiffLine('+new')).toBe('wsdiff-add');
    expect(classifyDiffLine('-old')).toBe('wsdiff-del');
    expect(classifyDiffLine('+++ b/x')).toBe('wsdiff-file');
    expect(classifyDiffLine('@@ -1 +1 @@')).toBe('wsdiff-hunk');
    expect(classifyDiffLine(' ctx')).toBe('wsdiff-ctx');
  });
});

describe('WorkspaceDiffPanel', () => {
  it('loads the diff and applies on click', async () => {
    render(<WorkspaceDiffPanel sessionId="s1" onChanged={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('+b')).toBeTruthy());
    fireEvent.click(screen.getByText('Apply to repo'));
    await waitFor(() => expect(applyAssistantWorkspace).toHaveBeenCalledWith('s1'));
    await waitFor(() => expect(screen.getByText(/applied to your working tree/i)).toBeTruthy());
  });

  it('warns when the diff is truncated', async () => {
    const api = await import('../../api/assistant.js');
    api.fetchAssistantWorkspaceDiff.mockResolvedValueOnce({ diff: 'diff --git a/x b/x\n+big\n', truncated: true, stats: [] });
    render(<WorkspaceDiffPanel sessionId="s1" onChanged={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    expect(screen.getByText(/truncated at 2 MB/i)).toBeTruthy();
  });

  it('keeps the buttons after a fail-soft PR (no prUrl)', async () => {
    const api = await import('../../api/assistant.js');
    api.createAssistantWorkspacePr.mockResolvedValueOnce({ prUrl: null, branch: 'b', pushed: false, message: 'Push failed. Branch kept.' });
    render(<WorkspaceDiffPanel sessionId="s1" onChanged={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('Apply to repo')).toBeTruthy());
    fireEvent.click(screen.getByText('Create PR...'));
    fireEvent.click(screen.getByText('Create PR'));
    await waitFor(() => expect(screen.getByText(/Push failed/i)).toBeTruthy());
    // still reviewable: Apply/Discard remain
    expect(screen.getByText('Apply to repo')).toBeTruthy();
    expect(screen.getByText('Discard')).toBeTruthy();
  });

  it('shows a terminal message when the branch pushed but no PR was created', async () => {
    const api = await import('../../api/assistant.js');
    api.createAssistantWorkspacePr.mockResolvedValueOnce({ prUrl: null, branch: 'b', pushed: true, message: 'Branch pushed. Open the PR from your git host.' });
    render(<WorkspaceDiffPanel sessionId="s1" onChanged={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('Apply to repo')).toBeTruthy());
    fireEvent.click(screen.getByText('Create PR...'));
    fireEvent.click(screen.getByText('Create PR'));
    await waitFor(() => expect(screen.getByText(/Branch pushed/i)).toBeTruthy());
    // terminal: Apply button is gone
    expect(screen.queryByText('Apply to repo')).toBeNull();
  });

  it('shows an empty-state message when there are no changes', async () => {
    const api = await import('../../api/assistant.js');
    api.fetchAssistantWorkspaceDiff.mockResolvedValueOnce({ diff: '', truncated: false, stats: [] });
    render(<WorkspaceDiffPanel sessionId="s1" onChanged={vi.fn()} />);
    await waitFor(() => expect(screen.getByText(/No changes in this worktree/i)).toBeTruthy());
  });

  it('does not discard when the confirm dialog is cancelled', async () => {
    confirmDialog.mockResolvedValueOnce(false);
    render(<WorkspaceDiffPanel sessionId="s1" onChanged={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('Discard')).toBeTruthy());
    fireEvent.click(screen.getByText('Discard'));
    await waitFor(() => expect(confirmDialog).toHaveBeenCalledWith(
      expect.objectContaining({ variant: 'danger' }),
    ));
    expect(discardAssistantWorkspace).not.toHaveBeenCalled();
  });

  it('discards when the confirm dialog is accepted', async () => {
    confirmDialog.mockResolvedValueOnce(true);
    render(<WorkspaceDiffPanel sessionId="s1" onChanged={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('Discard')).toBeTruthy());
    fireEvent.click(screen.getByText('Discard'));
    await waitFor(() => expect(discardAssistantWorkspace).toHaveBeenCalledWith('s1'));
  });
});

// Discriminating regression test for "Panel imports concrete API functions
// directly, bypassing the hook's DI": these tests supply the API functions
// only via a custom ApiProvider value (never via the module-level vi.mock
// above), so they can only pass if the Panel's Apply/Create PR/Discard
// buttons actually route through useWorkspaceDiff's useApi() resolution.
// Pre-fix, the Panel called the statically-imported functions from
// '../../api/assistant.js' and these fake ApiProvider functions would never
// be invoked.
describe('WorkspaceDiffPanel API injection', () => {
  it('routes "Apply to repo" through the injected ApiProvider', async () => {
    const fakeApi = makeFakeApi();
    render(
      <ApiProvider value={fakeApi}>
        <WorkspaceDiffPanel sessionId="s1" onChanged={vi.fn()} />
      </ApiProvider>,
    );
    await waitFor(() => expect(screen.getByText('+b')).toBeTruthy());
    fireEvent.click(screen.getByText('Apply to repo'));
    await waitFor(() => expect(fakeApi.applyAssistantWorkspace).toHaveBeenCalledWith('s1'));
    await waitFor(() => expect(screen.getByText(/applied to your working tree/i)).toBeTruthy());
  });

  it('routes "Create PR" through the injected ApiProvider', async () => {
    const fakeApi = makeFakeApi();
    render(
      <ApiProvider value={fakeApi}>
        <WorkspaceDiffPanel sessionId="s1" onChanged={vi.fn()} />
      </ApiProvider>,
    );
    await waitFor(() => expect(screen.getByText('Apply to repo')).toBeTruthy());
    fireEvent.click(screen.getByText('Create PR...'));
    fireEvent.click(screen.getByText('Create PR'));
    await waitFor(() => expect(fakeApi.createAssistantWorkspacePr).toHaveBeenCalledWith(
      's1', expect.objectContaining({ title: expect.any(String), body: '' }),
    ));
  });

  it('routes "Discard" (after confirm) through the injected ApiProvider', async () => {
    confirmDialog.mockResolvedValueOnce(true);
    const fakeApi = makeFakeApi();
    render(
      <ApiProvider value={fakeApi}>
        <WorkspaceDiffPanel sessionId="s1" onChanged={vi.fn()} />
      </ApiProvider>,
    );
    await waitFor(() => expect(screen.getByText('Discard')).toBeTruthy());
    fireEvent.click(screen.getByText('Discard'));
    await waitFor(() => expect(fakeApi.discardAssistantWorkspace).toHaveBeenCalledWith('s1'));
  });
});
