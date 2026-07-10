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

import { applyAssistantWorkspace } from '../../api/assistant.js';
import { WorkspaceDiffPanel, classifyDiffLine } from './WorkspaceDiffPanel.jsx';

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

  it('shows an empty-state message when there are no changes', async () => {
    const api = await import('../../api/assistant.js');
    api.fetchAssistantWorkspaceDiff.mockResolvedValueOnce({ diff: '', truncated: false, stats: [] });
    render(<WorkspaceDiffPanel sessionId="s1" onChanged={vi.fn()} />);
    await waitFor(() => expect(screen.getByText(/No changes in this worktree/i)).toBeTruthy());
  });
});
